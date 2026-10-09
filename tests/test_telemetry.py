"""Telemetry endpoint tests for TransformationSpine.

Tests the GET /api/v1/telemetry aggregated metrics endpoint
by overriding the CTST ledger with test data.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from spine.api import app as spine_app
from spine.ctst import CTSTLedger, CTSTRecord
from spine.result import ProviderResult


def _make_provider_result_with_telemetry(
    provider: str,
    error_signal: float = 0.0,
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
    total_tokens: int = 15,
) -> ProviderResult:
    """Build a ProviderResult with telemetry populated."""
    return ProviderResult(
        success=True,
        output=f"output from {provider}",
        provider=provider,
        model="mock-model",
        error_signal=error_signal,
        finished_reason="completed",
        usage={
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
        metadata={},
        telemetry={
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "error_signal": error_signal,
        },
    )


@pytest.fixture
def client_with_test_ledger():
    """Create a test client with a CTST ledger populated with test data."""
    # Create TestClient (this will run the lifespan and initialize globals)
    client = TestClient(spine_app)

    # Now override the CTST ledger with our test data
    import tempfile

    # Create a temporary ledger with test entries
    with tempfile.TemporaryDirectory() as tmpdir:
        test_ledger = CTSTLedger(tmpdir)

        # Add test entries
        test_entries: list[ProviderResult] = [
            _make_provider_result_with_telemetry(
                provider="llama.cpp",
                error_signal=0.0,
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            _make_provider_result_with_telemetry(
                provider="openai",
                error_signal=0.0,
                prompt_tokens=200,
                completion_tokens=100,
                total_tokens=300,
            ),
            _make_provider_result_with_telemetry(
                provider="anthropic",
                error_signal=0.5,  # partially converged
                prompt_tokens=150,
                completion_tokens=75,
                total_tokens=225,
            ),
        ]

        # Add entries to test ledger
        for result in test_entries:
            record = CTSTRecord(
                intent={"summary": f"telemetry test for {result.provider}"},
                context={},
                mechanism=result.provider,
                error_signal=result.error_signal,
                telemetry=result.telemetry,
            )
            test_ledger.append(record)

        # Override the global ctst_ledger in the spine.api module
        # We need to access the module and set the global
        import spine.api as api_module

        api_module.ctst_ledger = test_ledger

        yield client


def test_telemetry_endpoint_returns_200(client_with_test_ledger) -> None:
    """The /telemetry endpoint returns 200 with ledger data."""
    response = client_with_test_ledger.get("/api/v1/telemetry")
    assert response.status_code == 200


def test_telemetry_aggregates_by_provider(client_with_test_ledger) -> None:
    """Telemetry aggregates metrics by provider correctly."""
    response = client_with_test_ledger.get("/api/v1/telemetry")
    assert response.status_code == 200
    data = response.json()

    # Should have entries for each provider
    assert "providers" in data
    providers = data["providers"]
    assert set(providers.keys()) == {"llama.cpp", "openai", "anthropic"}

    # Check llama.cpp aggregates
    llama = providers["llama.cpp"]
    assert llama["prompt_tokens_avg"] == 100.0
    assert llama["completion_tokens_avg"] == 50.0
    assert llama["total_tokens_avg"] == 150.0
    assert llama["avg_error_signal"] == 0.0
    assert llama["runs"] == 1

    # Check openai aggregates
    openai = providers["openai"]
    assert openai["prompt_tokens_avg"] == 200.0
    assert openai["completion_tokens_avg"] == 100.0
    assert openai["total_tokens_avg"] == 300.0
    assert openai["avg_error_signal"] == 0.0
    assert openai["runs"] == 1

    # Check anthropic aggregates
    anthropic = providers["anthropic"]
    assert anthropic["prompt_tokens_avg"] == 150.0
    assert anthropic["completion_tokens_avg"] == 75.0
    assert anthropic["total_tokens_avg"] == 225.0
    assert anthropic["avg_error_signal"] == 0.5
    assert anthropic["runs"] == 1

    # Total ledger entries
    assert data["total_ledger_entries"] == 3


def test_telemetry_empty_ledger() -> None:
    """Telemetry endpoint handles empty ledger gracefully."""
    client = TestClient(spine_app)

    # Override with empty ledger
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        empty_ledger = CTSTLedger(tmpdir)
        import spine.api as api_module

        api_module.ctst_ledger = empty_ledger

        response = client.get("/api/v1/telemetry")
        assert response.status_code == 200
        data = response.json()

        assert data["providers"] == {}
        assert data["total_ledger_entries"] == 0
