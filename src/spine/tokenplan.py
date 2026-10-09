"""Token planner + route registry — the spine's token-efficiency engine.

Ported from the Token-Efficiency Engine spec (ENGINE-SPEC-v1) that runs
live in MyMilo (slices 1-3, v0.35-v0.37): DeepSeek behavior — never pay
tokens for context the model doesn't need, and never let output size be
an accident — implemented at the engine layer, since CSA/HCA are
weight-level and cannot be retrofitted into the models we serve.

Single source of truth for route limits: nothing else in the spine may
hardcode a context window or an output cap. Windows are the *serving*
reality (llama.cpp --ctx-size), not the model's nominal maximum — the
registry defaults are conservative and overridable per route via env:
SPINE_ROUTE_<NAME>_WINDOW / _DEFAULT_MAX / _MAX_OUT.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class ContextOverflowError(ValueError):
    """Raised when input alone cannot fit the route's window.

    The planner's n_ctx guard: curate or split the input BEFORE sending.
    The request is never sent to fail (or silently truncate) downstream.
    """


@dataclass(frozen=True)
class RouteSpec:
    """Serving limits for one provider route."""

    name: str
    context_window: int
    default_max_tokens: int
    max_output_tokens: int

    @property
    def margin(self) -> int:
        """Estimation-error reserve: max(256, 5% of window)."""
        return max(256, int(self.context_window * 0.05))


# Conservative serving defaults. llama.cpp routes reflect Aetheris
# serving flags (8K slots), not model-card maxima.
_ROUTE_DEFAULTS: dict[str, RouteSpec] = {
    "llama.cpp": RouteSpec("llama.cpp", 8192, 1024, 4096),
    "ollama": RouteSpec("ollama", 8192, 1024, 4096),
    "openai": RouteSpec("openai", 131072, 4096, 16384),
    "anthropic": RouteSpec("anthropic", 200000, 4096, 16384),
    "huggingface": RouteSpec("huggingface", 32768, 1024, 4096),
}

_FALLBACK = RouteSpec("unknown", 8192, 1024, 4096)


def route_spec(name: str) -> RouteSpec:
    """Look up a route's spec, applying per-route env overrides."""
    spec = _ROUTE_DEFAULTS.get(name, _FALLBACK)
    prefix = f"SPINE_ROUTE_{name.upper().replace('.', '_')}"
    window = os.environ.get(f"{prefix}_WINDOW")
    default_max = os.environ.get(f"{prefix}_DEFAULT_MAX")
    max_out = os.environ.get(f"{prefix}_MAX_OUT")
    if window or default_max or max_out:
        spec = RouteSpec(
            name=spec.name,
            context_window=int(window) if window else spec.context_window,
            default_max_tokens=int(default_max)
            if default_max
            else spec.default_max_tokens,
            max_output_tokens=int(max_out) if max_out else spec.max_output_tokens,
        )
    return spec


def estimate_tokens(text: str) -> int:
    """Pre-flight token estimate (calibrated char heuristic).

    Used for planning and triage only — the authoritative count is the
    provider's own ``usage`` after the call, which telemetry reconciles.
    The estimator is deliberately slightly conservative.
    """
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4 + 2)


def plan_max_tokens(
    spec: RouteSpec,
    estimated_input: int,
    desired: int | None = None,
) -> int:
    """Plan the output cap for one request on ``spec``'s route.

        planned = min(desired or route default, route max cap,
                      window - estimated_input - margin)

    Raises ContextOverflowError when the input alone leaves no room —
    the caller must curate/split before sending, never send and fail.
    """
    remaining = spec.context_window - estimated_input - spec.margin
    if remaining <= 0:
        raise ContextOverflowError(
            f"input needs ~{estimated_input} tokens but route '{spec.name}' "
            f"window is {spec.context_window} (margin {spec.margin}); "
            "curate or split the context before sending"
        )
    return min(desired or spec.default_max_tokens, spec.max_output_tokens, remaining)
