"""Caller-side gate evaluation — where the error signal actually comes from.

The Outcome Convergence doctrine (see result.py) says the error signal is
computed deterministically by caller-side gates, never by the model and
never merely copied from a transport status. Before this module existed,
adapters set error_signal to 0.0 on any HTTP success — so "converged"
meant "the call did not throw". This module is the computation that
claim always pointed at:

    error_signal = (sum of weights of failed checks) / (sum of weights)

over a fixed, versioned set of deterministic checks. Every check is a
pure function of the ProviderResult (plus an optional expected artifact),
so the same result always yields the same signal, on any machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .result import ProviderResult

_CLEAN_FINISHES = {"stop", "completed", "tool_calls", "end_turn"}


@dataclass(frozen=True)
class GateCheck:
    """One deterministic check in the gate evaluation."""

    name: str
    passed: bool
    weight: float
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "passed": self.passed,
            "weight": self.weight,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class GateReport:
    """Result of evaluating all gate checks for one provider result."""

    checks: list[GateCheck] = field(default_factory=list)
    error_signal: float = 1.0

    @property
    def converged(self) -> bool:
        return self.error_signal <= 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "error_signal": self.error_signal,
            "checks": [c.to_dict() for c in self.checks],
        }


def _token_similarity(a: str, b: str) -> float:
    """Jaccard similarity over normalized token sets (1.0 = identical)."""
    ta = set(a.lower().split())
    tb = set(b.lower().split())
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def evaluate_result(
    result: ProviderResult,
    *,
    expected_output: str | None = None,
) -> GateReport:
    """Compute the authoritative error signal for a provider result.

    Checks (weights in parentheses):
    - transport_success (3): the provider reports success.
    - output_present (2): the output is non-empty after stripping.
    - finished_cleanly (2): the finish reason is a clean stop, not a
      truncation ("length"/"max_tokens") or an error finish.
    - artifact_match (3, only when ``expected_output`` is given): token
      similarity between the output and the committed artifact the cycle
      was supposed to reproduce; contributes (1 - similarity) of its
      weight, so a partial match yields a partial signal.
    """
    checks: list[GateCheck] = []

    checks.append(
        GateCheck(
            name="transport_success",
            passed=bool(result.success),
            weight=3.0,
            detail="provider reported success" if result.success else "provider failed",
        )
    )

    has_output = bool((result.output or "").strip())
    checks.append(
        GateCheck(
            name="output_present",
            passed=has_output,
            weight=2.0,
            detail="non-empty output" if has_output else "empty output",
        )
    )

    clean_finish = result.finished_reason in _CLEAN_FINISHES
    checks.append(
        GateCheck(
            name="finished_cleanly",
            passed=clean_finish,
            weight=2.0,
            detail=f"finished_reason={result.finished_reason}",
        )
    )

    failed_weight = sum(c.weight for c in checks if not c.passed)
    total_weight = sum(c.weight for c in checks)

    if expected_output is not None:
        similarity = _token_similarity(result.output or "", expected_output)
        total_weight += 3.0
        failed_weight += 3.0 * (1.0 - similarity)
        checks.append(
            GateCheck(
                name="artifact_match",
                passed=similarity >= 1.0,
                weight=3.0,
                detail=f"token similarity={similarity:.3f}",
            )
        )

    error_signal = failed_weight / total_weight if total_weight else 1.0
    return GateReport(checks=checks, error_signal=round(error_signal, 6))
