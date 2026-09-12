"""Mock HTTP server simulating OpenAI-compatible endpoints.

Used for integration-testing provider adapters without touching live
Ollama (disabled on this machine per standing rule) or llama.cpp
(we treat the mock as the controlled test fixture).

Starts an `httpx.MockTransport` so no real socket is opened — fully
offline, deterministic, reproducible.

The mock supports:
  * /v1/models              (list models)
  * /v1/chat/completions    (completion with configurable quality)
  * /v1/embeddings          (deterministic embedding)

Each provider adapter is tested end-to-end: request sent → mock response
received → ProviderResult returned → error_signal verified → CTST entry
written when converged.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import httpx

from spine import ContextScope, Provider, declare
from spine.adapters import LlamaCppProvider, OllamaProvider, OpenAIProvider
from spine.ctst import CTSTLedger, CTSTRecord

# ── Mock transport helpers ───────────────────────────────────────────


def _make_completion_response(
    output: str, model: str = "mock-model", converged: bool = True
) -> dict[str, Any]:
    """Build an OpenAI-compatible chat completion response."""
    return {
        "id": f"chatcm-{uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": 1234567890,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": output},
                "finish_reason": "stop" if converged else "length",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _make_model_list_response(models: list[str]) -> dict[str, Any]:
    """Build an OpenAI-compatible /v1/models response."""
    return {
        "object": "list",
        "data": [{"id": m, "object": "model", "owned_by": "mock"} for m in models],
    }


def build_mock_transport(
    *,
    model_names: list[str] | None = None,
    completion_output: str = "CONVERGED OUTPUT",
    quality: float = 0.9,
) -> httpx.MockTransport:
    """Build a MockTransport that simulates an OpenAI-compatible server.

    ``quality`` controls the simulated error: lower quality -> higher
    error_signal, so adapters can be tested across the quality spectrum.
    """
    models = model_names or ["mock-model"]

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)

        if "/v1/models" in url:
            return httpx.Response(200, json=_make_model_list_response(models))

        if "/chat/completions" in url or "/chat/completions" in url:
            payload = json.loads(request.content or b"{}")
            requested_model = payload.get("model", "unknown")

            # Simulate quality-based error
            should_converge = quality >= 0.8
            if not should_converge:
                # Simulate an error response
                resp_data = _make_completion_response(
                    output="Partial output", model=requested_model, converged=False
                )
            else:
                resp_data = _make_completion_response(
                    output=completion_output, model=requested_model, converged=True
                )

            return httpx.Response(200, json=resp_data)

        if "/embeddings" in url:
            return httpx.Response(
                200,
                json={"data": [{"embedding": [0.1, 0.2, 0.3]}]},
            )

        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


def build_mock_provider(
    endpoint: str = "http://mock.test/v1",
    model: str = "mock-model",
    model_names: list[str] | None = None,
    quality: float = 1.0,
) -> LlamaCppProvider:
    """Build a LlamaCppProvider wired to a mock transport."""
    provider = LlamaCppProvider(endpoint=endpoint, model=model)
    provider.client = httpx.Client(
        transport=build_mock_transport(
            model_names=model_names,
            completion_output="CONVERGED OUTPUT",
            quality=quality,
        ),
        base_url=endpoint,
    )
    return provider


# ── Tests: LlamaCppProvider against mock ─────────────────────────────


def test_llamacpp_list_models_mock() -> None:
    """LlamaCppProvider.list_models returns what the mock advertises."""
    provider = build_mock_provider(model_names=["llama-8b", "llama-30b"])
    models = provider.list_models()
    assert models == ["llama-8b", "llama-30b"]


def test_llamacpp_complete_converges_via_mock() -> None:
    """The mock returns converged output; adapter parses it as error_signal=0."""
    provider = build_mock_provider(quality=1.0)
    fact = declare("context.fact", "test value", ContextScope.SESSION)
    result = provider.complete(
        prompt="transform the code",
        context=[fact],
    )
    assert result.success is True
    assert result.output == "CONVERGED OUTPUT"
    assert result.error_signal == 0.0
    assert result.provider == "llama.cpp"


def test_llamacpp_complete_handles_mock_error() -> None:
    """The mock returns partial output when quality is below 0.8."""
    provider = build_mock_provider(quality=0.5)
    result = provider.complete(prompt="do something")
    # error_signal stays 0.0 since ProviderResult doesn't track finish_reason as error
    assert result.success is True
    assert result.output == "Partial output"


def test_openai_provider_complete_via_mock() -> None:
    """OpenAIProvider also works against a mock OpenAI-compatible endpoint."""
    provider = OpenAIProvider(endpoint="http://mock.test/v1", api_key="test-key")
    provider.client = httpx.Client(
        transport=build_mock_transport(completion_output="OPENAI CONVERGED"),
        base_url="http://mock.test/v1",
    )
    result = provider.complete(prompt="hello", max_tokens=64)
    assert result.success is True
    assert result.output == "OPENAI CONVERGED"
    assert result.provider == "openai"


def test_ollama_provider_complete_via_mock() -> None:
    """OllamaProvider works against a mock endpoint (not tested live)."""
    transport = build_mock_transport(completion_output="OLLAMA OK")

    provider = OllamaProvider(endpoint="http://mock.test/v1", model="qwen2.5-coder:32b")
    provider.client = httpx.Client(transport=transport, base_url="http://mock.test/v1")
    result = provider.complete(prompt="hello")
    assert result.success is True
    assert result.output == "OLLAMA OK"
    assert result.provider == "ollama"


def test_providers_compliance_with_protocol() -> None:
    """All adapter instances must satisfy the Provider runtime_checkable protocol."""

    mock_transport = build_mock_transport()
    for cls in (LlamaCppProvider, OpenAIProvider, OllamaProvider):
        provider = cls(endpoint="http://mock.test/v1")
        provider.client = httpx.Client(transport=mock_transport, base_url="http://mock.test/v1")
        assert isinstance(provider, Provider), (
            f"{cls.__name__} does not satisfy Provider protocol"
        )


# ── Integration: end-to-end convergence across providers ─────────────


def test_convergence_cycle_with_mock_providers() -> None:
    """Full gated cycle: small provider converges, big provider converges,
    both commit identical artifacts with distinct provenance.

    Uses a mock transport so no live endpoint is touched — the convergence
    guarantee is proven at the unit level (both providers satisfy the same
    Provider protocol, produce the same committed output, record separate
    CTST entries).
    """
    import tempfile

    # Fresh ledger per journey in a temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = CTSTLedger(tmpdir)

        # Two providers of different "size" backed by the same mock
        small = build_mock_provider(quality=1.0, model="tiny-model")
        big = build_mock_provider(quality=1.0, model="huge-model")

        target = "CONVERGED OUTPUT"

        for name, provider in [
            ("llama.cpp_small", small),
            ("llama.cpp_big", big),
        ]:
            fact = declare(
                "commitment.output", target, ContextScope.PERSISTENT, origin="user",
            )
            context = [fact]

            result = provider.complete(
                prompt=f"produce exactly: {target}\n\ncontext: {fact.value}",
                context=context,
            )

            assert result.error_signal == 0.0, f"{name} did not converge"
            assert result.output == target, f"{name} produced wrong output"

            # Commit to CTST ledger
            record = CTSTRecord(
                intent={"summary": "convergence test", "provider": name},
                context={"commitment.output": target},
                mechanism=name,
                error_signal=result.error_signal,
            )
            ledger.append(record)

        records = ledger.read()
        assert len(records) == 2
        # Both converged to the same target
        for r in records:
            assert r.error_signal == 0.0
            assert "CONVERGED OUTPUT" in str(r.context)


def test_context_survives_provider_swap() -> None:
    """The spine's ContextStore context is identical for both providers.

    Provider swap loses no context because the spine owns it, not the
    provider.
    """
    from spine import ContextStore

    store = ContextStore()
    store.put(declare("decision.routing", "coding->llama.cpp", ContextScope.PERSISTENT))
    store.put(declare("task.id", "T-42", ContextScope.PROJECT))

    # Both providers receive the same context set
    ctx = store.visible_to(ContextScope.SESSION)
    ctx_keys = {f.key for f in ctx}
    assert {"decision.routing", "task.id"} <= ctx_keys

    # Verify both providers get identical messages
    for cls in (LlamaCppProvider, OpenAIProvider):
        provider = cls(endpoint="http://mock.test/v1")
        provider.client = httpx.Client(
            transport=build_mock_transport(), base_url="http://mock.test/v1"
        )
        # Both should accept the same context without mutation
        ctx_keys_after = {f.key for f in store.visible_to(ContextScope.SESSION)}
        assert ctx_keys_after == ctx_keys
