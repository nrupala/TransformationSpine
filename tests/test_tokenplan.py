"""Token planner + two-tier assembly tests (engine alignment PR).

Pins the Token-Efficiency Engine behavior ported from the live MyMilo
engine: planned output is bounded by the route window minus input and
margin; over-window input is refused before sending; assembly is
cache-stable, tier-budgeted, and relevance-ranked; session compaction
produces a checkpoint whose coverage is stated.
"""

from __future__ import annotations

import pytest

from spine.assembly import assemble_context
from spine.context import ContextScope, declare
from spine.store import ContextStore
from spine.tokenplan import (
    ContextOverflowError,
    estimate_tokens,
    plan_max_tokens,
    route_spec,
)


def test_plan_respects_window_margin_and_caps() -> None:
    spec = route_spec("llama.cpp")  # 8192 window, margin 409, max out 4096
    planned = plan_max_tokens(spec, estimated_input=1000)
    assert planned == spec.default_max_tokens  # 1024
    planned = plan_max_tokens(spec, estimated_input=1000, desired=99999)
    assert planned == spec.max_output_tokens  # 4096
    planned = plan_max_tokens(spec, estimated_input=7000, desired=4096)
    assert planned == 8192 - 7000 - spec.margin  # window-bound


def test_plan_refuses_over_window_input() -> None:
    spec = route_spec("llama.cpp")
    with pytest.raises(ContextOverflowError):
        plan_max_tokens(spec, estimated_input=8192)


def test_estimate_is_monotonic() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("a" * 100) < estimate_tokens("a" * 400)


def _fact(key: str, value: str, scope: ContextScope):  # type: ignore[no-untyped-def]
    return declare(key, value, scope, origin="test")


def test_assembly_prefix_is_stable_and_durable_first() -> None:
    facts = [
        _fact("session.note", "unrelated chatter", ContextScope.SESSION),
        _fact("project.rule", "always verify", ContextScope.PROJECT),
        _fact("global.const", "pi=3.14", ContextScope.PERSISTENT),
    ]
    a1 = assemble_context(facts, query="verify the build")
    a2 = assemble_context(facts, query="a totally different query")
    # Durable facts lead, in deterministic key order, whatever the query.
    assert a1.text.index("global.const") < a1.text.index("project.rule")
    assert a2.text.index("global.const") < a2.text.index("project.rule")
    assert a1.facts_used[:2] == ["global.const", "project.rule"]


def test_assembly_retrieval_prefers_relevant_facts() -> None:
    facts = [
        _fact("deploy.steps", "deploy with wrangler after tests", ContextScope.SESSION),
        _fact("lunch.menu", "sandwich soup salad", ContextScope.SESSION),
    ]
    a = assemble_context(facts, query="how do I deploy with wrangler")
    assert a.facts_used[0] == "deploy.steps"
    assert a.retrieval_tokens > 0


def test_assembly_respects_budget_and_reports_drops() -> None:
    big = "word " * 400  # ~2000 estimated tokens each
    facts = [_fact(f"k{i}", big, ContextScope.PROJECT) for i in range(6)]
    a = assemble_context(facts, budget_tokens=1500)
    assert a.estimated_tokens <= 1500 + 64  # estimator slack on the join
    assert a.facts_dropped, "over-budget facts must be reported, not vanished"


def test_assembly_summary_tier_is_capped_and_headed() -> None:
    summary = "long summary " * 500  # far beyond the 1024-token cap
    a = assemble_context([], summary=summary, summary_covers=12)
    assert "session-summary (covers 12 facts)" in a.text
    assert a.summary_tokens <= 1024 + 16


def test_transform_response_carries_token_plan(
    tmp_path, monkeypatch  # type: ignore[no-untyped-def]
) -> None:
    from fastapi.testclient import TestClient

    import spine.api as api_module
    from spine.result import ProviderResult

    seen: dict[str, int] = {}

    class _Fake:
        name = "fake"
        model = "m"

        def complete(self, **kwargs):  # type: ignore[no-untyped-def]
            seen["max_tokens"] = kwargs["max_tokens"]
            return ProviderResult(
                success=True,
                output="ok",
                provider="fake",
                model="m",
                error_signal=0.0,
                finished_reason="stop",
                usage={"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            )

    monkeypatch.setenv("SPINE_CTST_ROOT", str(tmp_path))
    api_module.provider_map["fake"] = _Fake()
    with TestClient(api_module.app) as client:
        resp = client.post(
            "/api/v1/transform", params={"intent": "hi", "provider": "fake"}
        )
    assert resp.status_code == 200
    plan = resp.json()["token_plan"]
    assert plan["context_window"] == 8192
    assert plan["planned_max_tokens"] == seen["max_tokens"]
    assert plan["planned_max_tokens"] != 512  # the old hardcoded cap is gone


def test_compact_session_checkpoint() -> None:
    store = ContextStore()
    store.open_session("s1")
    for i in range(3):
        store.put(declare(f"note.{i}", f"fact {i}", ContextScope.SESSION, owner="s1"))
    summary = store.compact_session("s1", "we decided X and Y")
    assert summary is not None
    assert summary.key == "session-summary:s1"
    assert summary.origin.startswith("compacted:3:from:")
    # The folded facts are gone; only the checkpoint remains.
    remaining = [
        f for f in store.query(scope=ContextScope.SESSION, owner="s1")
    ]
    assert [f.key for f in remaining] == ["session-summary:s1"]
    assert store.session_summary("s1") is summary
    # And the checkpoint flows into assembly's summary tier.
    a = assemble_context(
        [], summary=str(summary.value), summary_covers=3
    )
    assert "covers 3 facts" in a.text
