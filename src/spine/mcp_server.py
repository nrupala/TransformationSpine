# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: Apache-2.0
"""MCP server surface — the spine served to agents over MCP.

Implements the Model Context Protocol's core tool flow as JSON-RPC 2.0
(initialize / ping / tools/list / tools/call) with two transports:

- **Streamable HTTP** — ``POST /mcp`` on the FastAPI app (stateless;
  every request is one JSON-RPC message).
- **stdio** — ``spine mcp``, for agents that launch servers as
  subprocesses (the classic MCP host pattern).

Tools exposed:

- ``spine_transform`` — run one gated transformation cycle.
- ``spine_status`` — spine health + status.
- ``spine_context`` — rendered context for a scope.
- ``spine_ledger_verify`` — verify the CTST hash chain.
- ``spine_connector_execute`` — run any connector tool by name.
- One tool per discovered connector capability, named
  ``<connector>__<tool>``, so agent hosts can call them directly.
- The spine's built-in tools (echo / calculator / current_time).

The server is transport- and state-neutral: callables for the spine
operations are injected (``spine.api.build_mcp_server`` binds the live
app state), which keeps this module unit-testable without FastAPI.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TextIO

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "transformationspine"

TransformFn = Callable[..., dict[str, Any]]
StatusFn = Callable[[], dict[str, Any]]
ContextFn = Callable[[str], dict[str, Any]]
VerifyFn = Callable[[], dict[str, Any]]
ConnectorFn = Callable[[str, str, dict[str, Any]], dict[str, Any]]
ToolFnT = Callable[[dict[str, Any]], Any]


@dataclass
class MCPServer:
    """JSON-RPC handler for the MCP tool surface."""

    transform: TransformFn
    status: StatusFn
    context: ContextFn
    ledger_verify: VerifyFn
    connector_execute: ConnectorFn | None = None
    connector_tools: list[dict[str, Any]] = field(default_factory=list)
    spine_tools: dict[str, ToolFnT] = field(default_factory=dict)
    version: str = "0.2.0"

    # -- tool catalog ----------------------------------------------------

    def _catalog(self) -> list[dict[str, Any]]:
        obj = {"type": "object", "properties": {}}
        tools: list[dict[str, Any]] = [
            {
                "name": "spine_transform",
                "description": "Run one gated transformation cycle on the spine.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "intent": {"type": "string"},
                        "provider": {"type": "string", "default": "llama.cpp"},
                        "scope": {"type": "string", "default": "SESSION"},
                    },
                    "required": ["intent"],
                },
            },
            {
                "name": "spine_status",
                "description": "Spine health, providers, ledger size, safeguards.",
                "inputSchema": obj,
            },
            {
                "name": "spine_context",
                "description": "Rendered context facts visible to a scope.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"scope": {"type": "string", "default": "SESSION"}},
                },
            },
            {
                "name": "spine_ledger_verify",
                "description": "Verify the CTST ledger hash chain from disk.",
                "inputSchema": obj,
            },
            {
                "name": "spine_connector_execute",
                "description": "Execute a tool on any discovered connector.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "connector": {"type": "string"},
                        "tool": {"type": "string"},
                        "params": {"type": "object"},
                    },
                    "required": ["connector", "tool"],
                },
            },
        ]
        for ct in self.connector_tools:
            tools.append(
                {
                    "name": f"{ct['connector']}__{ct['tool']}",
                    "description": ct.get("description")
                    or f"{ct['tool']} on the {ct['connector']} connector.",
                    "inputSchema": ct.get(
                        "input_schema", {"type": "object", "properties": {}}
                    ),
                }
            )
        for name in sorted(self.spine_tools):
            tools.append(
                {
                    "name": name,
                    "description": f"Spine built-in tool '{name}'.",
                    "inputSchema": {"type": "object", "properties": {}},
                }
            )
        return tools

    # -- JSON-RPC handling -------------------------------------------------

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """Handle one JSON-RPC message; None means notification (no reply)."""
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params") or {}

        if req_id is None:  # notification
            return None

        if method == "initialize":
            return self._ok(
                req_id,
                {
                    "protocolVersion": params.get("protocolVersion", PROTOCOL_VERSION),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": self.version},
                },
            )
        if method == "ping":
            return self._ok(req_id, {})
        if method == "tools/list":
            return self._ok(req_id, {"tools": self._catalog()})
        if method == "tools/call":
            return self._ok(req_id, self._call_tool(params))
        return self._err(req_id, -32601, f"Method not found: {method}")

    @staticmethod
    def _ok(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    @staticmethod
    def _err(req_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params.get("name", ""))
        args = dict(params.get("arguments") or {})
        try:
            if name == "spine_transform":
                result: Any = self.transform(
                    intent=str(args["intent"]),
                    provider=str(args.get("provider", "llama.cpp")),
                    scope=str(args.get("scope", "SESSION")),
                )
            elif name == "spine_status":
                result = self.status()
            elif name == "spine_context":
                result = self.context(str(args.get("scope", "SESSION")))
            elif name == "spine_ledger_verify":
                result = self.ledger_verify()
            elif name == "spine_connector_execute":
                if self.connector_execute is None:
                    raise ValueError("connector execution is not configured")
                result = self.connector_execute(
                    str(args["connector"]),
                    str(args["tool"]),
                    dict(args.get("params") or {}),
                )
            elif "__" in name and self.connector_execute is not None:
                connector, _, tool = name.partition("__")
                result = self.connector_execute(connector, tool, args)
            elif name in self.spine_tools:
                result = self.spine_tools[name](args)
            else:
                return {
                    "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
                    "isError": True,
                }
        except Exception as e:  # tool failures are results, not RPC errors
            return {
                "content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}],
                "isError": True,
            }
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, default=str),
                }
            ],
            "isError": False,
        }


def serve_stdio(
    server: MCPServer,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> None:
    """Line-delimited JSON-RPC over stdio (the MCP subprocess pattern)."""
    src = stdin if stdin is not None else sys.stdin
    dst = stdout if stdout is not None else sys.stdout
    for line in src:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = server.handle(request)
        if response is not None:
            dst.write(json.dumps(response) + "\n")
            dst.flush()
