"""Agent + human surface tests: A2A, ACP, and the browser UI.

Every surface must run the same gated cycle: these tests drive A2A
message/send and an ACP run through a fake provider and check the
output — and for A2A, that the completed Task carries the cycle's
verdict metadata.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from spine.agent_surfaces import A2AAgent, ACPAgent, build_agent_card
from spine.result import ProviderResult


class _FakeProvider:
    name = "fake"
    model = "m"

    def complete(self, **kwargs: Any) -> ProviderResult:
        return ProviderResult(
            success=True,
            output="hello from fake",
            provider="fake",
            model="m",
            error_signal=0.0,
            finished_reason="stop",
            usage={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        )


def test_agent_card_shape() -> None:
    card = build_agent_card("0.2.0")
    assert card["name"] == "transformationspine"
    assert card["capabilities"]["streaming"] is False
    assert {s["id"] for s in card["skills"]} == {"transform", "connectors"}


def test_a2a_unit_flow() -> None:
    agent = A2AAgent(transform=lambda **kw: {"output": "done", "verdict": "PASS"})
    resp = agent.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "do it"}],
                }
            },
        }
    )
    assert resp is not None
    task = resp["result"]
    assert task["status"]["state"] == "completed"
    assert task["artifacts"][0]["parts"][0]["text"] == "done"

    got = agent.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tasks/get",
            "params": {"id": task["id"]},
        }
    )
    assert got is not None and got["result"]["id"] == task["id"]

    missing = agent.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tasks/get",
            "params": {"id": "nope"},
        }
    )
    assert missing is not None and missing["error"]["code"] == -32001


def test_acp_unit_flow() -> None:
    agent = ACPAgent(transform=lambda **kw: {"output": "acp-done", "verdict": "PASS"})
    run = agent.create_run({"input": "hello"})
    assert run["status"] == "completed"
    assert run["output"][0]["content"] == "acp-done"
    empty = agent.create_run({"input": ""})
    assert empty["status"] == "failed"
    parts = agent.create_run(
        {"input": [{"parts": [{"content_type": "text/plain", "content": "hi"}]}]}
    )
    assert parts["status"] == "completed"


def test_surfaces_over_http(tmp_path: Path, monkeypatch: Any) -> None:
    from fastapi.testclient import TestClient

    import spine.api as api_module

    monkeypatch.setenv("SPINE_CTST_ROOT", str(tmp_path))
    monkeypatch.setenv("SPINE_CONTEXT_PATH", str(tmp_path / "ctx.json"))
    api_module.provider_map["fake"] = _FakeProvider()
    with TestClient(api_module.app) as client:
        card = client.get("/.well-known/agent-card.json")
        assert card.status_code == 200
        assert card.json()["name"] == "transformationspine"

        task_resp = client.post(
            "/a2a",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"kind": "text", "text": "say hello"}],
                        "metadata": {"provider": "fake"},
                    }
                },
            },
        )
        assert task_resp.status_code == 200
        task = task_resp.json()["result"]
        assert task["status"]["state"] == "completed"
        assert task["artifacts"][0]["parts"][0]["text"] == "hello from fake"
        assert task["metadata"]["verdict"] == "commit"

        agents = client.get("/acp/agents")
        assert agents.status_code == 200
        assert agents.json()[0]["name"] == "transformationspine"

        run = client.post(
            "/acp/agents/transformationspine/runs",
            json={"input": "say hello", "provider": "fake"},
        )
        assert run.status_code == 200
        run_body = run.json()
        assert run_body["status"] == "completed"
        assert run_body["output"][0]["content"] == "hello from fake"

        fetched = client.get(
            f"/acp/agents/transformationspine/runs/{run_body['run_id']}"
        )
        assert fetched.status_code == 200
        assert fetched.json()["run_id"] == run_body["run_id"]

        assert (
            client.post("/acp/agents/ghost/runs", json={"input": "x"}).status_code
            == 404
        )
        assert (
            client.get("/acp/agents/transformationspine/runs/nope").status_code == 404
        )

        ui = client.get("/ui")
        assert ui.status_code == 200
        assert "TransformationSpine" in ui.text
        assert "/api/v1/transform" in ui.text
