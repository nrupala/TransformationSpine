"""Result and convergence types shared by spine providers.

The Outcome Convergence framing, adopted from the OCS repos
(``D:/ocs-software``, ``D:/ocscoder``): every state transition produces a
``ProviderResult`` carrying an error signal, so convergence across providers
is measurable regardless of which engine produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class ProviderResult:
    """Outcome of a single provider call.

    ``error_signal`` is normalized to [0,1]: the spine's universal currency
    for judging a model's work. 0.0 = entirely converged (all gates green),
    1.0 = total failure. It is computed deterministically by the caller-side
    gates — never by another model (LLM-verifies-LLM is forbidden).
    """

    success: bool
    output: str
    provider: str
    model: str
    error_signal: float = 1.0
    finished_reason: str = "completed"
    usage: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: str = ""
    telemetry: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Telemetry is derived from usage at construction, so every
        # adapter that reports usage (all of them) populates telemetry —
        # before this, the field existed but no code path ever filled it,
        # and the /telemetry endpoint aggregated permanent zeros.
        if not self.telemetry and self.usage:
            self.telemetry = {
                k: self.usage[k]
                for k in ("prompt_tokens", "completion_tokens", "total_tokens")
                if k in self.usage
            }

    @property
    def is_converged(self) -> bool:
        """A result converged when the error signal reached zero."""
        return self.error_signal <= 0.0

    @property
    def gap(self) -> float:
        """Gap to convergence; alias kept for OCS compatibility."""
        return self.error_signal
