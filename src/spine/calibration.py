# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Estimator calibration — the token engine's slice 4 (ENGINE-SPEC-v1).

The char heuristic in spine.tokenplan is a prior: cheap, deterministic,
and off by a route-specific amount. Providers report the authoritative
input count in their usage block after every call, and this module
reconciles the two. Per route it keeps the most recent samples of
(estimated, actual), derives the correction factor
``total_actual / total_estimated`` over that window, and — once the
route has enough samples to trust — scales new estimates by it.

Spec rules:
  * window: the most recent 200 samples per route;
  * factor clamped to [0.5, 2.0];
  * the factor is APPLIED only at >= 20 samples; below that the applied
    factor is 1.0, though the observed bias is still reported;
  * ``calibration_warning`` when |bias| > 10% at >= 20 samples, where
    bias_pct is the signed error of the raw heuristic over the window
    (positive: actuals run higher than estimates).

Persistence: samples live in a JSON file at ``SPINE_CALIBRATION_PATH``,
defaulting to ``calibration.json`` under ``SPINE_LOG_DIR`` (default
``./logs``). Writes are temp-file + rename, and every failure is
swallowed: calibration is an optimization and must never break a
transform.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from spine.tokenplan import estimate_tokens

WINDOW = 200
MIN_SAMPLES = 20
FACTOR_MIN = 0.5
FACTOR_MAX = 2.0
WARNING_BIAS_PCT = 10.0


def default_calibration_path() -> Path:
    """Resolve where the calibration file lives (env-first)."""
    override = os.environ.get("SPINE_CALIBRATION_PATH")
    if override:
        return Path(override)
    log_dir = os.environ.get("SPINE_LOG_DIR") or "./logs"
    return Path(log_dir) / "calibration.json"


class Calibrator:
    """Per-route reconciliation of estimated vs actual input tokens."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path if path is not None else default_calibration_path()
        self._samples: dict[str, list[tuple[int, int]]] = {}
        self._lock = threading.Lock()
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    # ── recording ────────────────────────────────────────────────────

    def record(self, route: str, estimated: int, actual: int) -> None:
        """Keep one (estimated, actual) sample for ``route``.

        Samples need a known route, a positive estimate, and a positive
        actual. A zero actual means the provider reported no usage —
        absence of evidence, not evidence — so it is dropped rather
        than allowed to poison the factor.
        """
        if not route or estimated <= 0 or actual <= 0:
            return
        with self._lock:
            bucket = self._samples.setdefault(route, [])
            bucket.append((int(estimated), int(actual)))
            del bucket[:-WINDOW]
            self._save_locked()

    # ── derived state ────────────────────────────────────────────────

    def sample_count(self, route: str) -> int:
        return len(self._samples.get(route, ()))

    def _window_ratio(self, route: str) -> float | None:
        """total_actual / total_estimated over the window (None if empty)."""
        bucket = self._samples.get(route)
        if not bucket:
            return None
        estimated_total = sum(e for e, _ in bucket)
        if estimated_total <= 0:
            return None
        return sum(a for _, a in bucket) / estimated_total

    def factor(self, route: str) -> float:
        """The correction factor actually applied for ``route``.

        1.0 until the route reaches MIN_SAMPLES; then the window ratio
        clamped to [FACTOR_MIN, FACTOR_MAX].
        """
        if self.sample_count(route) < MIN_SAMPLES:
            return 1.0
        ratio = self._window_ratio(route)
        if ratio is None:
            return 1.0
        return min(FACTOR_MAX, max(FACTOR_MIN, ratio))

    def bias_pct(self, route: str) -> float:
        """Signed bias of the raw heuristic over the window, in percent.

        Positive means providers report MORE input tokens than the
        heuristic estimated. 0.0 when the route has no samples.
        """
        ratio = self._window_ratio(route)
        if ratio is None:
            return 0.0
        return (ratio - 1.0) * 100.0

    def warning(self, route: str) -> bool:
        """True when a trusted route's bias exceeds the spec threshold.

        The comparison carries a 1e-9 tolerance: a bias that is
        mathematically exactly at the threshold (e.g. 2200/2000) must
        not trip the rule on floating-point dust (10.000000000000009).
        """
        return (
            self.sample_count(route) >= MIN_SAMPLES
            and abs(self.bias_pct(route)) > WARNING_BIAS_PCT + 1e-9
        )

    def state(self, route: str) -> dict[str, Any]:
        """JSON-ready calibration summary for one route."""
        return {
            "route": route,
            "samples": self.sample_count(route),
            "factor": round(self.factor(route), 4),
            "bias_pct": round(self.bias_pct(route), 2),
            "calibration_warning": self.warning(route),
        }

    def snapshot(self) -> dict[str, Any]:
        """JSON-ready calibration summary for every known route."""
        return {route: self.state(route) for route in sorted(self._samples)}

    # ── estimation ───────────────────────────────────────────────────

    def scale_estimate(self, raw_estimate: int, route: str) -> int:
        """Scale an existing raw estimate by the route's applied factor."""
        if raw_estimate <= 0:
            return 0
        return max(1, round(raw_estimate * self.factor(route)))

    def calibrated_estimate(self, text: str, route: str) -> int:
        """estimate_tokens(text) scaled by the route's applied factor."""
        return self.scale_estimate(estimate_tokens(text), route)

    # ── persistence (best-effort) ────────────────────────────────────

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            routes = data.get("routes", {})
            loaded: dict[str, list[tuple[int, int]]] = {}
            for route, samples in routes.items():
                bucket = [
                    (int(e), int(a)) for e, a in samples if int(e) > 0 and int(a) > 0
                ]
                if bucket:
                    loaded[str(route)] = bucket[-WINDOW:]
            self._samples = loaded
        except Exception:
            # Missing or corrupt file: start empty. Calibration relearns.
            self._samples = {}

    def _save_locked(self) -> None:
        """Persist samples (temp file + rename). Never raises."""
        tmp: str | None = None
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "routes": {
                    route: [[e, a] for e, a in bucket]
                    for route, bucket in self._samples.items()
                },
            }
            fd, tmp = tempfile.mkstemp(
                dir=str(self._path.parent),
                prefix=".calibration-",
                suffix=".tmp",
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp, self._path)
            tmp = None
        except Exception:
            pass
        finally:
            if tmp is not None:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
