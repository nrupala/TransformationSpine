"""Agent invocation adapters for prebuilt agent skills."""

from __future__ import annotations

import subprocess
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
    """A prebuilt agent skill that can be invoked."""

    name: str
    entry_point: Path
    description: str

    def invoke(self, *args: str, **kwargs: Any) -> AgentResult:
        """Invoke the agent skill with the given arguments."""
        cmd = ["python", str(self.entry_point), *args]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return AgentResult(
                success=result.returncode == 0,
                output=result.stdout,
                errors=result.stderr.splitlines() if result.stderr else [],
                metadata={"returncode": result.returncode},
            )
        except subprocess.TimeoutExpired:
            return AgentResult(
                success=False,
                output="",
                errors=["Agent invocation timed out"],
                metadata={},
            )


def load_agent_skill(name: str) -> AgentSkill | None:
    """Load a prebuilt agent skill by name."""
    skill_dir = Path(__file__).resolve().parent.parent.parent / "skills" / name
    entry = skill_dir / "SKILL.md"
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
    return ""


def list_agent_skills() -> list[str]:
    """List all available agent skills."""
    skill_dir = Path(__file__).resolve().parent.parent.parent / "skills"
    skills = []
    if skill_dir.exists():
        for d in sorted(skill_dir.iterdir()):
            if d.is_dir() and (d / "SKILL.md").exists():
                skills.append(d.name)
    return skills


def code_review(path: str) -> AgentResult:
    """Run code review on the given path using ruff and mypy."""
    p = Path(path).resolve()
    errors: list[str] = []
    output_parts: list[str] = []

    for tool in ["ruff", "mypy"]:
        cmd = ["python", "-m", tool]
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
                errors.extend(
                    (result.stderr or result.stdout).splitlines()
                )
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
    """Generate pytest content for a module."""
    name = mod.stem
    return f'''"""Auto-generated tests for {name}."""

from __future__ import annotations

import pytest


def test_module_exists() -> None:
    """Verify the module can be imported."""
    import importlib
    importlib.import_module("{mod.stem}")
'''
