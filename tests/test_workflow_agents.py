"""Workflow execution + agents + safeguard tests (audit F-08/F-09/F-07).

F-08: the workflow module was authoring-only — no execution, no cycle
check. F-09: agent discovery always returned [] (wrong path), invoke()
tried to execute a Markdown file, generate_tests emitted a fixed
template, two advertised agents did not exist. F-07 (safeguard half):
enforce_safeguards reported changes it never made.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import pytest

from spine.agents import (
    generate_tests,
    list_agent_skills,
    load_agent_skill,
    prompt_optimizer,
    rag_query,
)
from spine.safeguard import enforce_safeguards, world_writable_count
from spine.workflow import (
    build_default_handlers,
    execute_workflow,
    topological_order,
    validate_workflow,
    workflow_from_template,
)


def test_discovery_finds_repo_skills() -> None:
    skills = list_agent_skills()
    assert "code-review-agent" in skills
    assert "test-generator-agent" in skills
    assert "prompt-optimizer-agent" in skills
    skill = load_agent_skill("code-review-agent")
    assert skill is not None
    assert "Code Review" in skill.instructions()


def test_doc_only_skill_invoke_is_honest(tmp_path: Path) -> None:
    skill = load_agent_skill("code-review-agent")
    assert skill is not None
    result = skill.invoke()  # no args -> no implementation dispatch
    assert result.success is False
    assert "instructions()" in result.errors[0]


def test_prompt_optimizer_actually_transforms() -> None:
    result = prompt_optimizer(
        "Please note that  this is a test.\n\n\n\nSecond line.   "
    )
    assert "Please note that" not in result.output
    assert result.metadata["chars_after"] < result.metadata["chars_before"]


def test_rag_query_retrieves_relevant() -> None:
    docs = [
        "the deploy pipeline uses wrangler and cloudflare",
        "lunch today is soup and sandwiches",
        "wrangler deploy steps for the worker",
    ]
    result = rag_query(docs, "wrangler deploy", k=2)
    assert result.metadata["retrieved"] == 2
    assert "soup" not in result.output
    assert result.metadata["method"] == "lexical-jaccard"


def test_generate_tests_uses_real_ast(tmp_path: Path) -> None:
    mod = tmp_path / "sample_mod.py"
    mod.write_text("def alpha():\n    pass\n\n\nclass Beta:\n    pass\n")
    out = tmp_path / "test_sample_mod.py"
    result = generate_tests(str(mod), str(out))
    assert result.success is True
    content = out.read_text()
    assert "test_alpha_exists_and_is_callable" in content
    assert "test_Beta_exists_and_is_callable" in content


def test_workflow_cycle_detected() -> None:
    wf = workflow_from_template("cyc")
    wf.edges.append(type(wf.edges[0])(from_node="output", to_node="input"))
    errors = validate_workflow(wf)
    assert any("cycle" in e for e in errors)
    with pytest.raises(ValueError, match="cycle"):
        topological_order(wf)


def test_workflow_execution_and_gate() -> None:
    wf = workflow_from_template("demo")
    handlers = build_default_handlers(store=None, provider=None, ledger=None)
    run = execute_workflow(wf, handlers, initial_state={"input": "hi"})
    # No provider -> error_signal 1.0 -> gate blocks before ledger.append.
    assert run.status == "gate_failed"
    assert run.failed_node == "verify"
    assert run.order == ["input", "context", "provider", "verify"]


def test_workflow_execution_full_pass() -> None:
    class _Provider:
        def complete(self, **kw: Any):  # type: ignore[no-untyped-def]
            from spine.result import ProviderResult

            return ProviderResult(
                success=True,
                output="done",
                provider="fake",
                model="m",
                error_signal=0.0,
            )

    class _Ledger:
        def append(self, record: Any) -> str:
            return "hash-abc"

    wf = workflow_from_template("demo")
    handlers = build_default_handlers(
        store=None, provider=_Provider(), ledger=_Ledger()
    )
    run = execute_workflow(wf, handlers, initial_state={"input": "hi"})
    assert run.status == "completed"
    assert run.outputs["commit"] == "hash-abc"


def test_safeguard_enforce_really_chmods(tmp_path: Path) -> None:
    f = tmp_path / "loose.txt"
    f.write_text("x")
    os.chmod(f, 0o666)
    assert world_writable_count(tmp_path) >= 1
    changes = enforce_safeguards(tmp_path)
    assert changes, "enforce must report the change it applied"
    mode = stat.S_IMODE(f.stat().st_mode)
    assert mode & 0o002 == 0
    assert world_writable_count(tmp_path) == 0
    # Second run is a no-op — no fictional changes.
    assert enforce_safeguards(tmp_path) == []
