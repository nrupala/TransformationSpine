"""MCP server surface tests: JSON-RPC handler, stdio, HTTP transport."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from spine.mcp_server import MCPServer, serve_stdio


def _server() -> MCPServer:
    return MCPServer(
        transform=lambda **kw: {"output": f"did:{kw['intent']}", "verdict": "PASS"},
        status=lambda: {"status": "ok", "providers": ["llama.cpp"]},
        context=lambda scope: {"scope": scope, "rendered": "facts"},
        ledger_verify=lambda: {"valid": True, "records": 3},
        connector_execute=lambda c, t, p: {
            "connector": c,
            "tool": t,
            "success": True,
            "output": p,
        },
        connector_tools=[
            {
                "connector": "github",
                "tool": "list_issues",
                "description": "List issues.",
                "input_schema": {"type": "object", "properties": {}},
            }
        ],
        spine_tools={"calculator": lambda a: 42},
        version="0.2.0",
    )


def _rpc(server: MCPServer, method: str, params: dict | None = None) -> dict:
    resp = server.handle(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    )
    assert resp is not None
    return resp


def test_initialize_and_ping() -> None:
    server = _server()
    init = _rpc(server, "initialize", {"protocolVersion": "2024-11-05"})
    assert init["result"]["serverInfo"]["name"] == "transformationspine"
    assert init["result"]["protocolVersion"] == "2024-11-05"
    assert _rpc(server, "ping")["result"] == {}


def test_notification_gets_no_reply() -> None:
    server = _server()
    assert (
        server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    )


def test_unknown_method_is_jsonrpc_error() -> None:
    resp = _rpc(_server(), "resources/list")
    assert resp["error"]["code"] == -32601


def test_tools_list_includes_all_surfaces() -> None:
    tools = _rpc(_server(), "tools/list")["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {
        "spine_transform",
        "spine_status",
        "spine_context",
        "spine_ledger_verify",
        "spine_connector_execute",
        "github__list_issues",
        "calculator",
    } <= names


def test_tools_call_transform_and_connector() -> None:
    server = _server()
    out = _rpc(
        server,
        "tools/call",
        {"name": "spine_transform", "arguments": {"intent": "summarize"}},
    )["result"]
    assert out["isError"] is False
    assert "did:summarize" in out["content"][0]["text"]

    dyn = _rpc(
        server,
        "tools/call",
        {"name": "github__list_issues", "arguments": {"repo": "x"}},
    )["result"]
    assert dyn["isError"] is False
    assert '"repo": "x"' in dyn["content"][0]["text"]

    calc = _rpc(server, "tools/call", {"name": "calculator", "arguments": {}})["result"]
    assert calc["content"][0]["text"] == "42"


def test_tools_call_errors_are_results_not_rpc_errors() -> None:
    server = _server()
    unknown = _rpc(server, "tools/call", {"name": "nope", "arguments": {}})["result"]
    assert unknown["isError"] is True

    missing_arg = _rpc(
        server, "tools/call", {"name": "spine_transform", "arguments": {}}
    )["result"]
    assert missing_arg["isError"] is True
    assert "intent" in missing_arg["content"][0]["text"]


def test_stdio_roundtrip() -> None:
    server = _server()
    lines = "\n".join(
        [
            json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
            ),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "spine_status", "arguments": {}},
                }
            ),
            "not json at all",
        ]
    )
    out = io.StringIO()
    serve_stdio(server, stdin=io.StringIO(lines), stdout=out)
    replies = [json.loads(x) for x in out.getvalue().splitlines()]
    assert [r["id"] for r in replies] == [1, 2]
    assert '"status": "ok"' in replies[1]["result"]["content"][0]["text"]


def test_http_mcp_endpoint(tmp_path: Path, monkeypatch: Any) -> None:
    from fastapi.testclient import TestClient

    import spine.api as api_module

    monkeypatch.setenv("SPINE_CTST_ROOT", str(tmp_path))
    monkeypatch.setenv("SPINE_CONTEXT_PATH", str(tmp_path / "ctx.json"))
    with TestClient(api_module.app) as client:
        init = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        assert init.status_code == 200
        assert init.json()["result"]["serverInfo"]["name"] == "transformationspine"

        verify = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "spine_ledger_verify", "arguments": {}},
            },
        )
        assert verify.status_code == 200
        payload = json.loads(verify.json()["result"]["content"][0]["text"])
        assert payload["valid"] is True

        note = client.post(
            "/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        assert note.status_code == 202
