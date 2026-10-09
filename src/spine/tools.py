# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tool registry and execution loop — tool calls that actually run.

Audit F-10: adapters parsed ``tool_calls`` out of provider responses
and nothing ever executed them — no registry, no dispatch, no result
round-trip, and the BUILD_PLAN-promised ``tools.yaml`` did not exist.
This module is that missing layer:

- ``ToolRegistry`` maps tool names to callables plus their OpenAI-format
  definitions. Definitions load from ``tools.yaml``; executors are
  bound to the built-ins below (deliberately small and safe: no file
  system, no shell, no network — tools that need the world belong in
  connectors, behind their own credentials).
- ``run_tool_loop`` drives the round-trip: provider returns tool calls
  → registry executes them → results go back to the provider → final
  answer. Bounded rounds; every execution is recorded on the result's
  metadata so the CTST ledger shows what ran.
"""

from __future__ import annotations

import ast
import json
import operator
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .context import ContextFact
    from .provider import Provider
    from .result import ProviderResult

ToolFn = Callable[[dict[str, Any]], Any]


# ── Built-in tools ───────────────────────────────────────────────────


def _tool_echo(args: dict[str, Any]) -> str:
    return str(args.get("text", ""))


def _tool_current_time(args: dict[str, Any]) -> str:
    return datetime.now(UTC).isoformat()


_BIN_OPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}


def _eval_arith(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_arith(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return float(
            _BIN_OPS[type(node.op)](_eval_arith(node.left), _eval_arith(node.right))
        )
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_arith(node.operand)
    raise ValueError("only numeric arithmetic expressions are allowed")


def _tool_calculator(args: dict[str, Any]) -> float:
    expr = str(args.get("expression", ""))
    return _eval_arith(ast.parse(expr, mode="eval"))


BUILTIN_TOOLS: dict[str, ToolFn] = {
    "echo": _tool_echo,
    "current_time": _tool_current_time,
    "calculator": _tool_calculator,
}


# ── Registry ─────────────────────────────────────────────────────────


class ToolRegistry:
    """Named tool definitions + executors."""

    def __init__(self) -> None:
        self._defs: dict[str, dict[str, Any]] = {}
        self._fns: dict[str, ToolFn] = {}

    def register(
        self,
        name: str,
        fn: ToolFn,
        *,
        description: str = "",
        parameters: dict[str, Any] | None = None,
    ) -> None:
        self._fns[name] = fn
        self._defs[name] = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters or {"type": "object", "properties": {}},
            },
        }

    def definitions(self) -> list[dict[str, Any]]:
        """OpenAI-format tool definitions for every registered tool."""
        return list(self._defs.values())

    def names(self) -> list[str]:
        return sorted(self._fns)

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Run one tool; failures return an error dict, never raise."""
        fn = self._fns.get(name)
        if fn is None:
            return {"tool": name, "ok": False, "error": f"unknown tool: {name}"}
        try:
            output = fn(arguments)
        except Exception as e:  # tool errors are data for the model
            return {"tool": name, "ok": False, "error": f"{type(e).__name__}: {e}"}
        return {"tool": name, "ok": True, "output": output}

    @classmethod
    def from_yaml(cls, path: str | Path) -> ToolRegistry:
        """Load tool definitions from tools.yaml, binding built-in executors.

        Entries name a ``builtin`` executor; entries naming an unknown
        builtin are skipped (definitions without executors would be a
        promise the spine cannot keep).
        """
        import yaml

        registry = cls()
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        for entry in data.get("tools", []) or []:
            builtin = entry.get("builtin", "")
            fn = BUILTIN_TOOLS.get(builtin)
            if fn is None:
                continue
            registry.register(
                entry["name"],
                fn,
                description=entry.get("description", ""),
                parameters=entry.get("parameters"),
            )
        return registry

    @classmethod
    def defaults(cls) -> ToolRegistry:
        """Registry with every built-in registered under its own name."""
        registry = cls()
        for name, fn in BUILTIN_TOOLS.items():
            registry.register(name, fn, description=f"Built-in tool: {name}")
        return registry


# ── Execution loop ───────────────────────────────────────────────────


def _normalize_call(call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Accept both spine shape {name, arguments} and OpenAI wire shape
    {function: {name, arguments: "<json>"}}."""
    if "function" in call:
        fn = call.get("function") or {}
        name = fn.get("name", "")
        raw = fn.get("arguments", {})
    else:
        name = call.get("name", "")
        raw = call.get("arguments", {})
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            raw = {"_raw": raw}
    return str(name), dict(raw) if isinstance(raw, dict) else {"value": raw}


def run_tool_loop(
    provider: Provider,
    prompt: str,
    context: list[ContextFact],
    registry: ToolRegistry,
    *,
    max_tokens: int = 512,
    max_rounds: int = 2,
) -> ProviderResult:
    """Complete with tool execution: call → execute → feed back → answer.

    The provider receives the registry's tool definitions. When it
    answers with tool calls, each is executed and the results are
    appended to the prompt for the next round (providers here are
    stateless workers; the round-trip rides the prompt). Stops when a
    round returns no tool calls or ``max_rounds`` is reached. The final
    result's metadata records every execution under ``tool_executions``.
    """
    tools = registry.definitions()
    result = provider.complete(
        prompt=prompt,
        context=context,
        max_tokens=max_tokens,
        temperature=0.0,
        tools=tools,
    )
    executions: list[dict[str, Any]] = []
    rounds = 0
    while result.tool_calls and rounds < max_rounds:
        rounds += 1
        lines = []
        for call in result.tool_calls:
            name, args = _normalize_call(call)
            outcome = registry.execute(name, args)
            executions.append(outcome)
            lines.append(
                f"Tool {name} result: {outcome.get('output', outcome.get('error'))}"
            )
        follow_up = (
            f"{prompt}\n\n" + "\n".join(lines) + "\n\nNow answer the original "
            "request using the tool results above. Do not call more tools "
            "unless essential."
        )
        result = provider.complete(
            prompt=follow_up,
            context=context,
            max_tokens=max_tokens,
            temperature=0.0,
            tools=tools,
        )
    if executions:
        result.metadata = {**result.metadata, "tool_executions": executions}
    return result
