# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Estimator calibration tests (engine slice 4, ENGINE-SPEC-v1).

Pins the reconciliation loop: per-route (estimated, actual) samples,
a correction factor = total_actual / total_estimated over the most
recent 200 samples, clamped to [0.5, 2.0], applied only at >= 20
samples, a warning when a trusted route's bias exceeds 10%, JSON
persistence that survives restarts, and the API wiring that shifts
planned estimates once a route has learned.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from spine.calibration import Calibrator, default_calibration_path
from spine.tokenplan import estimate_tokens

ROUTE = "llama.cpp"


def _cal(tmp_path: Path, name: str = "cal.json") -> Calibrator:
    return Calibrator(tmp_path / name)


def _feed(cal: Calibrator, route: str, estimated: int, actual: int, n: int) -> None:
    for _ in range(n):
        cal.record(route, estimated, actual)


def test_factor_is_one_below_threshold_but_bias_is_reported(
    tmp_path: Path,
) -> None:
    cal = _cal(tmp_path)
    _feed(cal, ROUTE, 100, 200, 19)  # one short of MIN_SAMPLES
    assert cal.sample_count(ROUTE) == 19
    assert cal.factor(ROUTE) == 1.0  # not applied yet
    assert cal.bias_pct(ROUTE) == pytest.approx(100.0)  # still reported
    assert cal.warning(ROUTE) is False  # warning needs trusted samples


def test_factor_applies_at_threshold(tmp_path: Path) -> None:
    cal = _cal(tmp_path)
    _feed(cal, ROUTE, 100, 150, 20)
    assert cal.factor(ROUTE) == pytest.approx(1.5)
    assert cal.bias_pct(ROUTE) == pytest.approx(50.0)
    assert cal.warning(ROUTE) is True


def test_warning_boundary_is_strictly_greater_than_ten_pct(
    tmp_path: Path,
) -> None:
    cal = _cal(tmp_path)
    _feed(cal, ROUTE, 100, 110, 20)  # bias exactly +10%
    assert cal.bias_pct(ROUTE) == pytest.approx(10.0)
    assert cal.warning(ROUTE) is False
    cal2 = _cal(tmp_path, "cal2.json")
    _feed(cal2, ROUTE, 100, 111, 20)  # bias +11%
    assert cal2.warning(ROUTE) is True
    cal3 = _cal(tmp_path, "cal3.json")
    _feed(cal3, ROUTE, 100, 95, 20)  # bias -5%: over-estimating, no warning
    assert cal3.bias_pct(ROUTE) == pytest.approx(-5.0)
    assert cal3.warning(ROUTE) is False


def test_factor_is_clamped_both_ways(tmp_path: Path) -> None:
    cal = _cal(tmp_path)
    _feed(cal, ROUTE, 100, 400, 20)  # raw ratio 4.0
    assert cal.factor(ROUTE) == 2.0
    assert cal.bias_pct(ROUTE) == pytest.approx(300.0)  # bias stays honest
    cal2 = _cal(tmp_path, "cal2.json")
    _feed(cal2, ROUTE, 200, 50, 20)  # raw ratio 0.25
    assert cal2.factor(ROUTE) == 0.5


def test_window_keeps_only_most_recent_200(tmp_path: Path) -> None:
    cal = _cal(tmp_path)
    _feed(cal, ROUTE, 100, 100, 200)
    _feed(cal, ROUTE, 100, 200, 50)  # evicts the oldest 50 samples
    assert cal.sample_count(ROUTE) == 200
    # Window is now 150x(100,100) + 50x(100,200): ratio 25000/20000.
    assert cal.factor(ROUTE) == pytest.approx(1.25)


def test_invalid_samples_are_dropped(tmp_path: Path) -> None:
    cal = _cal(tmp_path)
    cal.record("", 100, 100)  # unknown route
    cal.record(ROUTE, 0, 100)  # no estimate
    cal.record(ROUTE, -5, 100)
    cal.record(ROUTE, 100, 0)  # provider reported no usage
    cal.record(ROUTE, 100, -1)
    assert cal.sample_count(ROUTE) == 0
    assert cal.snapshot() == {}


def test_unknown_route_defaults(tmp_path: Path) -> None:
    cal = _cal(tmp_path)
    assert cal.factor("nope") == 1.0
    assert cal.bias_pct("nope") == 0.0
    assert cal.warning("nope") is False
    assert cal.state("nope") == {
        "route": "nope",
        "samples": 0,
        "factor": 1.0,
        "bias_pct": 0.0,
        "calibration_warning": False,
    }


def test_calibrated_estimate_scales_raw_heuristic(tmp_path: Path) -> None:
    text = "x" * 100
    raw = estimate_tokens(text)
    assert raw > 0
    cal = _cal(tmp_path)
    assert cal.calibrated_estimate(text, ROUTE) == raw  # nothing learned
    _feed(cal, ROUTE, 100, 200, 20)  # factor 2.0
    assert cal.calibrated_estimate(text, ROUTE) == raw * 2
    assert cal.calibrated_estimate("", ROUTE) == 0
    assert cal.scale_estimate(0, ROUTE) == 0


def test_persistence_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "cal.json"
    cal = Calibrator(path)
    _feed(cal, ROUTE, 100, 150, 25)
    _feed(cal, "openai", 50, 50, 3)
    assert path.exists()
    reloaded = Calibrator(path)
    assert reloaded.sample_count(ROUTE) == 25
    assert reloaded.factor(ROUTE) == pytest.approx(1.5)
    assert reloaded.sample_count("openai") == 3
    assert set(reloaded.snapshot()) == {ROUTE, "openai"}


def test_corrupt_file_starts_empty(tmp_path: Path) -> None:
    path = tmp_path / "cal.json"
    path.write_text("{not json", encoding="utf-8")
    cal = Calibrator(path)
    assert cal.snapshot() == {}
    cal.record(ROUTE, 100, 100)  # and recording still works
    assert cal.sample_count(ROUTE) == 1


def test_failed_write_never_breaks_recording(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory", encoding="utf-8")
    cal = Calibrator(blocker / "cal.json")  # parent can never be created
    cal.record(ROUTE, 100, 150)  # must not raise
    assert cal.sample_count(ROUTE) == 1  # in-memory state still kept


def test_default_path_env_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SPINE_CALIBRATION_PATH", str(tmp_path / "x.json"))
    assert default_calibration_path() == tmp_path / "x.json"
    monkeypatch.delenv("SPINE_CALIBRATION_PATH")
    monkeypatch.setenv("SPINE_LOG_DIR", str(tmp_path / "logs"))
    assert default_calibration_path() == tmp_path / "logs" / "calibration.json"


def test_api_estimate_shifts_after_learning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: a pre-learned route plans with the calibrated
    estimate, the response carries the calibration state, the cycle's
    actual is recorded, and status/telemetry surface the state."""
    from fastapi.testclient import TestClient

    import spine.api as api_module
    from spine.result import ProviderResult

    cal_path = tmp_path / "calibration.json"
    cal_path.write_text(
        json.dumps({"version": 1, "routes": {"openai": [[100, 200]] * 20}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("SPINE_CALIBRATION_PATH", str(cal_path))
    monkeypatch.setenv("SPINE_CTST_ROOT", str(tmp_path))
    monkeypatch.setenv("SPINE_CONTEXT_PATH", str(tmp_path / "ctx.json"))

    class _Fake:
        name = "openai"
        model = "m"

        def complete(self, **kwargs):  # type: ignore[no-untyped-def]
            return ProviderResult(
                success=True,
                output="ok",
                provider="openai",
                model="m",
                error_signal=0.0,
                finished_reason="stop",
                usage={"prompt_tokens": 42, "completion_tokens": 2, "total_tokens": 44},
            )

    api_module.provider_map["openai"] = _Fake()
    with TestClient(api_module.app) as client:
        resp = client.post(
            "/api/v1/transform", params={"intent": "hi", "provider": "openai"}
        )
        assert resp.status_code == 200
        plan = resp.json()["token_plan"]
        # Learned factor 2.0 applied to the raw heuristic estimate.
        assert plan["calibration"]["factor"] == 2.0
        assert plan["calibration"]["samples"] == 20
        assert plan["calibration"]["calibration_warning"] is True
        assert plan["estimated_input_tokens"] == plan["raw_estimated_input_tokens"] * 2

        status = client.get("/api/v1/status")
        assert status.status_code == 200
        assert status.json()["calibration"]["openai"]["factor"] == 2.0

        telemetry = client.get("/api/v1/telemetry")
        assert telemetry.status_code == 200
        assert telemetry.json()["calibration"]["openai"]["samples"] == 21

    # The completed cycle recorded its (raw estimate, actual) sample and
    # persisted it: the fake reported 42 prompt tokens.
    saved = json.loads(cal_path.read_text(encoding="utf-8"))
    samples = saved["routes"]["openai"]
    assert len(samples) == 21
    assert samples[-1] == [plan["raw_estimated_input_tokens"], 42]
