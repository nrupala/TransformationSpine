# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Agent invocation adapters for prebuilt agent skills."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AgentResult:
    """Result from an agent invocation."""

    success: bool
    output: str
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentSkill:
    """A prebuilt agent skill.

    Skills are SKILL.md instruction documents (prompt skills), not
    executables. ``instructions()`` returns the document for the caller
    to load into context; ``invoke()`` dispatches to the spine's real
    Python implementation for the skills that have one
    (code-review-agent, test-generator-agent, prompt-optimizer-agent)
    and reports honestly for documentation-only skills. (The previous
    implementation tried to execute the SKILL.md file itself as a
    Python script, which could never work.)
    """

    name: str
    entry_point: Path
    description: str

    def instructions(self) -> str:
        """Return the skill's SKILL.md document text."""
        return self.entry_point.read_text(encoding="utf-8")

    def invoke(self, *args: str, **kwargs: Any) -> AgentResult:
        """Run the skill's implementation, where one exists.

        Argument conventions mirror the underlying functions:
        code-review-agent(path), test-generator-agent(module, output),
        prompt-optimizer-agent(prompt_text).
        """
        if self.name == "code-review-agent" and args:
            return code_review(args[0])
        if self.name == "test-generator-agent" and len(args) >= 2:
            return generate_tests(args[0], args[1])
        if self.name == "prompt-optimizer-agent" and args:
            return prompt_optimizer(args[0])
        return AgentResult(
            success=False,
            output="",
            errors=[
                f"Skill '{self.name}' is a documentation (prompt) skill "
                "with no executable implementation; load it via "
                "instructions() instead of invoke()."
            ],
            metadata={"skill": self.name},
        )


def _skills_root() -> Path | None:
    """Locate the skills directory.

    Resolution order: SPINE_SKILLS_DIR env, the repo checkout root
    (four levels up from this file: agents -> spine -> src -> root),
    then ./skills under the current directory. (The previous code
    stopped one level short, at src/skills, which does not exist —
    discovery therefore always returned [].)
    """
    env = os.environ.get("SPINE_SKILLS_DIR")
    candidates = [
        Path(env) if env else None,
        Path(__file__).resolve().parent.parent.parent.parent / "skills",
        Path.cwd() / "skills",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.exists():
            return candidate
    return None


def load_agent_skill(name: str) -> AgentSkill | None:
    """Load a prebuilt agent skill by name."""
    root = _skills_root()
    if root is None:
        return None
    entry = root / name / "SKILL.md"
    if entry.exists():
        return AgentSkill(
            name=name,
            entry_point=entry,
            description=_parse_description(entry),
        )
    return None


def _parse_description(entry: Path) -> str:
    """Parse the description from a SKILL.md YAML header."""
    text = entry.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("description:"):
            return line.split("description:", 1)[1].strip().strip('"')
    # SKILL.md files here carry a purpose section instead of a
    # frontmatter description; fall back to the first heading line.
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def list_agent_skills() -> list[str]:
    """List all available agent skills."""
    root = _skills_root()
    if root is None:
        return []
    return sorted(
        d.name for d in root.iterdir() if d.is_dir() and (d / "SKILL.md").exists()
    )


def code_review(path: str) -> AgentResult:
    """Run code review on the given path using ruff and mypy."""
    p = Path(path).resolve()
    errors: list[str] = []
    output_parts: list[str] = []

    for tool in ["ruff", "mypy"]:
        cmd = [sys.executable, "-m", tool]
        if tool == "ruff":
            cmd.append("check")
        cmd.append(str(p))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.stdout:
                output_parts.append(result.stdout)
            if result.returncode != 0:
                errors.extend((result.stderr or result.stdout).splitlines())
        except subprocess.TimeoutExpired:
            errors.append(f"{tool} timed out")

    return AgentResult(
        success=len(errors) == 0,
        output="\n".join(output_parts),
        errors=errors,
        metadata={"tool": "ruff,mypy", "path": str(p)},
    )


def generate_tests(module: str, output: str) -> AgentResult:
    """Generate a basic pytest file for the given module."""
    mod = Path(module)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    test_content = _generate_test_content(mod)
    out.write_text(test_content, encoding="utf-8")
    return AgentResult(
        success=True,
        output=f"Generated tests at {out}",
        errors=[],
        metadata={"module": module, "output": str(out)},
    )


def _generate_test_content(mod: Path) -> str:
    """Generate pytest content for a module, from its real AST.

    One existence/callability test per public function and class the
    module actually defines — the previous generator emitted the same
    fixed template for every module despite claiming AST-based
    generation in its docstring.
    """
    tree = ast.parse(mod.read_text(encoding="utf-8"))
    module_name = mod.stem
    lines = [
        f'''"""Auto-generated tests for {module_name}."""''',
        "",
        "from __future__ import annotations",
        "",
        f"import {module_name}",
        "",
        "",
        "def test_module_exists() -> None:",
        f"    assert {module_name} is not None",
    ]
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("_"):
                continue
            lines += [
                "",
                "",
                f"def test_{node.name}_exists_and_is_callable() -> None:",
                f"    assert callable({module_name}.{node.name})",
            ]
    return "\n".join(lines) + "\n"


_FILLER_PHRASES = (
    "please note that",
    "it is important to note that",
    "as an ai language model,",
    "as an ai,",
    "i hope this helps",
    "let me know if you need anything else",
)


def prompt_optimizer(prompt: str) -> AgentResult:
    """Optimize a prompt deterministically (prompt-optimizer-agent).

    Real, reproducible transforms — no model call: collapse excess
    whitespace and blank lines, strip known filler phrases, trim each
    line, and report the size change. Structure is never invented;
    content is never reworded beyond the filler list.
    """
    original_len = len(prompt)
    text = prompt
    removed: list[str] = []
    lowered = text.lower()
    for phrase in _FILLER_PHRASES:
        if phrase in lowered:
            removed.append(phrase)
    for phrase in _FILLER_PHRASES:
        # case-insensitive removal of the phrase wherever it appears
        idx = text.lower().find(phrase)
        while idx != -1:
            text = text[:idx] + text[idx + len(phrase) :]
            idx = text.lower().find(phrase)
    lines = [line.strip() for line in text.splitlines()]
    compacted: list[str] = []
    blank = False
    for line in lines:
        if line:
            compacted.append(line)
            blank = False
        elif not blank:
            compacted.append("")
            blank = True
    optimized = "\n".join(compacted).strip()
    return AgentResult(
        success=True,
        output=optimized,
        errors=[],
        metadata={
            "chars_before": original_len,
            "chars_after": len(optimized),
            "filler_removed": removed,
        },
    )


def rag_query(documents: list[str], query: str, k: int = 3) -> AgentResult:
    """Retrieve the top-k documents for a query (rag-pipeline-agent).

    Lexical retrieval — token-overlap (Jaccard) scoring over the given
    corpus, ranked, with scores reported. This is honest lexical RAG:
    no embeddings are claimed; swap the scorer when a vector backend
    is configured. Documents with zero overlap are excluded.
    """
    query_tokens = set(query.lower().split())
    scored: list[tuple[float, int, str]] = []
    for idx, doc in enumerate(documents):
        tokens = set(doc.lower().split())
        if not tokens or not query_tokens:
            continue
        score = len(tokens & query_tokens) / len(tokens | query_tokens)
        if score > 0:
            scored.append((score, idx, doc))
    scored.sort(key=lambda t: (-t[0], t[1]))
    top = scored[:k]
    output = "\n\n".join(f"[score={score:.3f}] {doc}" for score, _idx, doc in top)
    return AgentResult(
        success=True,
        output=output,
        errors=[],
        metadata={
            "retrieved": len(top),
            "scores": [round(s, 4) for s, _i, _d in top],
            "method": "lexical-jaccard",
        },
    )
