"""Tool execution loop tests (audit F-10).

Before the fix, adapters parsed tool_calls and nothing executed them.
These tests drive a scripted provider through the registry loop: the
first completion asks for the calculator, the registry must run it,
and the second completion must receive the computed result.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from spine.context import ContextFact
from spine.result import ProviderResult
from spine.tools import ToolRegistry, run_tool_loop

ROOT = Path(__file__).resolve().parent.parent


def test_registry_loads_tools_yaml() -> None:
    registry = ToolRegistry.from_yaml(ROOT / "tools.yaml")
    assert registry.names() == ["calculator", "current_time", "echo"]
    defs = registry.definitions()
    assert all(d["type"] == "function" for d in defs)


def test_calculator_is_real_and_safe() -> None:
    registry = ToolRegistry.defaults()
    out = registry.execute("calculator", {"expression": "2 * (3 + 4)"})
    assert out == {"tool": "calculator", "ok": True, "output": 14.0}
    bad = registry.execute("calculator", {"expression": "__import__('os')"})
    assert bad["ok"] is False
    unknown = registry.execute("nope", {})
    assert unknown["ok"] is False


class _ScriptedProvider:
    name = "scripted"
    model = "m"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(
        self, prompt: str, context: list[ContextFact] | None = None, **kw: Any
    ) -> ProviderResult:
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            assert kw.get("tools"), "provider must be offered tool definitions"
            return ProviderResult(
                success=True,
                output="",
                provider=self.name,
                model=self.model,
                finished_reason="tool_calls",
                tool_calls=[
                    {
                        "function": {
                            "name": "calculator",
                            "arguments": '{"expression": "6 * 7"}',
                        }
                    }
                ],
            )
        return ProviderResult(
            success=True,
            output="The answer is 42.",
            provider=self.name,
            model=self.model,
            finished_reason="stop",
        )


def test_tool_loop_executes_and_feeds_back() -> None:
    provider = _ScriptedProvider()
    registry = ToolRegistry.from_yaml(ROOT / "tools.yaml")
    result = run_tool_loop(provider, "what is 6*7?", [], registry)
    assert result.output == "The answer is 42."
    # The second prompt carried the executed result back to the provider.
    assert "42.0" in provider.prompts[1]
    executions = result.metadata["tool_executions"]
    assert executions[0]["tool"] == "calculator"
    assert executions[0]["output"] == 42.0


def test_tool_loop_bounded_rounds() -> None:
    class _AlwaysTools:
        name = "loopy"
        model = "m"

        def complete(
            self, prompt: str, context: Any = None, **kw: Any
        ) -> ProviderResult:
            return ProviderResult(
                success=True,
                output="",
                provider=self.name,
                model=self.model,
                finished_reason="tool_calls",
                tool_calls=[{"name": "echo", "arguments": {"text": "x"}}],
            )

    result = run_tool_loop(
        _AlwaysTools(), "go", [], ToolRegistry.defaults(), max_rounds=2
    )
    assert len(result.metadata["tool_executions"]) == 2
