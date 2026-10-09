"""Adapter sweep: every HTTP adapter's complete/list/embed paths via
httpx MockTransport (audit F-11 coverage for adapters.py)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from spine.adapters import LlamaCppProvider, OllamaProvider, OpenAIProvider


def _client(payload: Any, status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


_CHAT = {
    "choices": [
        {
            "message": {"role": "assistant", "content": "sweep reply"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15},
}


def test_llama_complete_and_models() -> None:
    p = LlamaCppProvider(endpoint="http://x:8830", model="m")
    p.client = _client(_CHAT)
    r = p.complete("hi")
    assert r.success and r.output == "sweep reply"
    assert r.telemetry["total_tokens"] == 15
    p.client = _client({"data": [{"id": "a"}, {"id": "b"}]})
    assert p.list_models() == ["a", "b"]
    p.client = _client({}, status=500)
    r = p.complete("hi")
    assert r.success is False and r.error_signal == 1.0


def test_llama_embed() -> None:
    p = LlamaCppProvider(endpoint="http://x:8830", model="m")
    p.client = _client({"data": [{"embedding": [0.1, 0.2, 0.3]}]})
    assert p.embed("text") == [0.1, 0.2, 0.3]


def test_ollama_complete() -> None:
    p = OllamaProvider(endpoint="http://x:11434/v1", model="m")
    p.client = _client(_CHAT)
    r = p.complete("hi")
    assert r.success and r.output == "sweep reply"
    p.client = _client({"models": [{"name": "qwen"}]})
    assert "qwen" in str(p.list_models())


def test_openai_complete_and_error() -> None:
    p = OpenAIProvider(endpoint="https://api.example/v1", api_key="k", model="m")
    p.client = _client(_CHAT)
    r = p.complete("hi")
    assert r.success and r.output == "sweep reply"
    p.client = _client({"error": "bad"}, status=429)
    r = p.complete("hi")
    assert r.success is False


def test_openai_tool_call_parsing() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "echo", "arguments": "{}"},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }
    p = LlamaCppProvider(endpoint="http://x:8830", model="m")
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=payload)

    p.client = httpx.Client(transport=httpx.MockTransport(handler))
    r = p.complete("hi", tools=[{"type": "function", "function": {"name": "echo"}}])
    assert r.tool_calls, "tool calls must be parsed out of the response"
    assert captured["body"]["tools"], "tools must be sent in the request"
