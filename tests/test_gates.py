"""Gate-evaluation and end-to-end telemetry tests (audit F-03/F-07).

F-03: before the fix, the gated cycle trusted the adapter's binary
error_signal (0.0 on any HTTP success). These tests pin the caller-side
computation in spine.gates: the same result must always yield the same
signal, and a truncated/empty/failed result must not read as converged.

F-07: a full /transform cycle must leave a CTST record whose committed
flag, telemetry, and error signal reflect what happened, and /telemetry
must aggregate those real values (not permanent zeros).
"""

from __future__ import annotations

from typing import Any

import pytest

from spine.gates import evaluate_result
from spine.result import ProviderResult


def _result(**overrides: Any) -> ProviderResult:
    base: dict[str, Any] = {
        "success": True,
        "output": "hello world",
        "provider": "fake",
        "model": "m",
        "error_signal": 0.0,
        "finished_reason": "stop",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    base.update(overrides)
    return ProviderResult(**base)


def test_clean_result_converges() -> None:
    report = evaluate_result(_result())
    assert report.error_signal == 0.0
    assert report.converged is True


def test_failed_transport_is_not_converged() -> None:
    report = evaluate_result(_result(success=False, output=""))
    # transport (3) + output (2) fail of 7 total
    assert report.error_signal == pytest.approx(5 / 7)
    assert report.converged is False


def test_truncated_output_carries_partial_signal() -> None:
    report = evaluate_result(_result(finished_reason="length"))
    assert report.error_signal == pytest.approx(2 / 7)


def test_artifact_match_exact_and_partial() -> None:
    exact = evaluate_result(_result(output="a b c"), expected_output="a b c")
    assert exact.error_signal == 0.0
    partial = evaluate_result(_result(output="a b x"), expected_output="a b c")
    # similarity 2/4 = 0.5 -> half of weight 3 fails, of 10 total
    assert partial.error_signal == pytest.approx(1.5 / 10)


def test_telemetry_derived_from_usage() -> None:
    r = _result()
    assert r.telemetry["prompt_tokens"] == 10
    assert r.telemetry["total_tokens"] == 15


class _FakeProvider:
    name = "fake"
    model = "m"

    def complete(self, **kwargs: Any) -> ProviderResult:
        return _result(provider="fake")


def test_transform_writes_full_ctst_record_and_telemetry(
    tmp_path: Any, monkeypatch: Any
) -> None:
    from fastapi.testclient import TestClient

    import spine.api as api_module
    from spine.ctst import CTSTLedger

    # The lifespan builds its ledger from SPINE_CTST_ROOT; point it at tmp
    # so the API's own ledger is the one we inspect afterwards.
    monkeypatch.setenv("SPINE_CTST_ROOT", str(tmp_path))
    api_module.provider_map["fake"] = _FakeProvider()
    with TestClient(api_module.app) as client:
        resp = client.post(
            "/api/v1/transform",
            params={"intent": "say hello", "provider": "fake"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["committed"] is True
        assert body["error_signal"] == 0.0
        assert body["gates"]["checks"]

        tel = client.get("/api/v1/telemetry").json()

    records = CTSTLedger(root=tmp_path).query()
    assert len(records) == 1
    rec = records[0]
    assert rec.committed is True
    assert rec.error_signal == 0.0
    assert rec.outcome["output"] == "hello world"
    assert rec.telemetry["prompt_tokens"] == 10
    assert "latency_ms" in rec.telemetry
    # /telemetry aggregated the real record, not zeros
    assert tel["providers"]["fake"]["prompt_tokens_avg"] == 10.0
    assert tel["providers"]["fake"]["runs"] == 1
