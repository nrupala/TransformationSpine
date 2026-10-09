# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: Apache-2.0
"""Provider abstraction — the spine's contract with any inference engine.

The whole point of the spine is **provider neutrality**: switching from
Anthropic to llama.cpp (or Codex to a local 8B) must lose nothing but the
model's own capability. Every provider seen by the spine — cloud API, local
llama.cpp router, OpenAI-compatible endpoint, an agent CLI like opencode — is
wrapped behind this protocol.

The interface is small, deterministic, and testable with fakes. No spine code
ever talks to a provider's SDK directly; that keeps the swap cost ~0 and the
convergence guarantees provider-independent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .context import ContextFact, ContextScope
from .result import ProviderResult


@runtime_checkable
class Provider(Protocol):
    """Every engine the spine can drive implements this protocol.

    Engines may optionally implement tool use by setting ``tool_calls`` in
    ProviderResult and returning tool execution results via the ``tools``
    argument in complete().
    """

    name: str
    endpoint: str

    def list_models(self) -> list[str]:
        """Return model identifiers this provider can serve."""
        ...

    def complete(
        self,
        prompt: str,
        context: list[ContextFact],
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ProviderResult:
        """Run one deterministic completion against the provider.

        ``context`` is passed explicitly — the provider is a stateless worker;
        it does not own memory. The spine assembles context, the provider just
        consumes it. This is the "models are workers" principle made concrete.

        Args:
            tools: Optional list of tool definitions in OpenAI function format.
                  If provided, the provider may return tool calls in
                  ProviderResult.tool_calls.
        """
        ...

    def embed(self, text: str, model: str | None = None) -> list[float]:
        """Embed ``text`` (used by the vector/knowledge layer). Optional."""
        ...


@dataclass(frozen=True)
class ModelSpec:
    """A provider's named model plus declared strengths and tags.

    Mirrors ``Providers.yaml`` but as a typed, go-able structure.
    """

    provider: str
    model: str
    strengths: tuple[str, ...] = ()
    endpoint: str = ""
    tags: frozenset[str] = frozenset()

    @classmethod
    def from_yaml(cls, data: dict[str, Any]) -> list[ModelSpec]:
        """Build ModelSpecs from the repo's ``Providers.yaml`` shape.

        Returns specs across ALL profiles. (The previous implementation
        iterated only flat sections and silently dropped the nested
        cloud/hybrid provider dicts — most of the file never parsed.)
        """
        from .factory import parse_provider_specs

        specs: list[ModelSpec] = []
        for profile_specs in parse_provider_specs(data).values():
            specs.extend(profile_specs)
        return specs


@dataclass
class RouterRule:
    """A named routing decision: task kind -> provider/model + fallback."""

    task: str
    primary_provider: str
    primary_model: str
    fallback_provider: str = ""
    fallback_model: str = ""
    min_scope: ContextScope = ContextScope.SESSION

    def matches(self, task: str) -> bool:
        """Whether this rule should be consulted for a task kind."""
        return task == self.task

    @classmethod
    def from_yaml(cls, cfg: dict[str, Any], profile: str = "local") -> list[RouterRule]:
        """Build rules from the repo's ``Routing.yaml`` shape with profile selection.

        Provider names are canonicalized (Routing.yaml says "local";
        adapters register as "llama.cpp") so a rule's provider can be
        looked up in a provider map without a translation step.
        """
        from .factory import canonical_provider

        def canon(name: str) -> str:
            return canonical_provider(name) if name else ""

        rules: list[RouterRule] = []
        # Support both flat structure (legacy) and profile-aware structure
        if profile in cfg.get("routes", {}):
            # Profile-aware structure: routes -> profile -> task -> {primary, fallback}
            profile_routes = cfg["routes"][profile]
            for task, route in profile_routes.items():
                primary = route.get("primary") or {}
                fallback = route.get("fallback") or {}
                # Support local_fallback for hybrid
                local_fallback = route.get("local_fallback") or {}
                rules.append(
                    cls(
                        task=task,
                        primary_provider=canon(primary.get("provider", "")),
                        primary_model=primary.get("model", ""),
                        fallback_provider=canon(fallback.get("provider", "")),
                        fallback_model=fallback.get("model", ""),
                    )
                )
                # If there's a local_fallback, create an additional rule with higher
                # priority for sensitive tasks
                if local_fallback and "local_sensitive" in task:
                    rules.append(
                        cls(
                            task=task,
                            primary_provider=canon(local_fallback.get("provider", "")),
                            primary_model=local_fallback.get("model", ""),
                            min_scope=ContextScope.PROJECT,
                        )
                    )
        else:
            # Legacy flat structure: routes -> task -> {primary, fallback}
            for task, route in (cfg.get("routes") or {}).items():
                primary = route.get("primary") or {}
                fallback = route.get("fallback") or {}
                rules.append(
                    cls(
                        task=task,
                        primary_provider=canon(primary.get("provider", "")),
                        primary_model=primary.get("model", ""),
                        fallback_provider=canon(fallback.get("provider", "")),
                        fallback_model=fallback.get("model", ""),
                    )
                )
        return rules
