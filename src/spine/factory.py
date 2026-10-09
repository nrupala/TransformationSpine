"""Provider factory — profiles and routing that actually take effect.

Audit F-06: Providers.yaml / Routing.yaml existed and RouterRule could
parse them, but nothing in the CLI or API ever built providers from a
profile, ModelSpec.from_yaml silently dropped the nested cloud/hybrid
sections, and the CLI ignored the profile outright. This module is the
missing wiring:

- ``parse_provider_specs`` understands all three shapes in the repo's
  Providers.yaml (flat endpoint section, nested per-provider cloud
  section, hybrid primary/fallback entries) and drops nothing.
- ``create_provider`` instantiates the adapter for one spec, returning
  None when a required credential is absent (cloud providers without a
  key are skipped, never half-built).
- ``build_provider_map`` assembles the adapter map for a profile.
- ``select_for_task`` resolves a Routing.yaml task rule, with fallback.
"""

from __future__ import annotations

import os
from typing import Any

from .provider import ModelSpec, Provider, RouterRule

# Providers.yaml profile sections name the endpoint families; the
# adapters register under their own names.
_PROVIDER_ALIASES = {
    "local": "llama.cpp",
    "llama.cpp": "llama.cpp",
    "llamacpp": "llama.cpp",
    "ollama": "ollama",
    "openai": "openai",
    "anthropic": "anthropic",
    "huggingface": "huggingface",
}


def canonical_provider(name: str) -> str:
    return _PROVIDER_ALIASES.get(name.lower(), name.lower())


def _specs_from_section(
    provider_label: str, cfg: dict[str, Any]
) -> list[ModelSpec]:
    specs: list[ModelSpec] = []
    endpoint = cfg.get("endpoint", "")
    strengths = tuple(cfg.get("strengths", []))
    for model in cfg.get("models", []) or []:
        specs.append(
            ModelSpec(
                provider=canonical_provider(provider_label),
                model=model,
                strengths=strengths,
                endpoint=endpoint,
            )
        )
    # Hybrid shape: {primary: {provider, model}, fallback: {...}, ...}
    for role in ("primary", "fallback", "local_sensitive"):
        entry = cfg.get(role)
        if isinstance(entry, dict) and entry.get("model"):
            specs.append(
                ModelSpec(
                    provider=canonical_provider(entry.get("provider", "")),
                    model=entry["model"],
                    strengths=(role,),
                    endpoint=endpoint,
                )
            )
    return specs


def parse_provider_specs(data: dict[str, Any]) -> dict[str, list[ModelSpec]]:
    """Parse Providers.yaml into per-profile ModelSpecs (nothing dropped)."""
    profiles: dict[str, list[ModelSpec]] = {}
    for profile, section in (data.get("providers") or {}).items():
        specs: list[ModelSpec] = []
        if not isinstance(section, dict):
            continue
        if section.get("models") or section.get("endpoint"):
            specs.extend(_specs_from_section(profile, section))
        for label, cfg in section.items():
            if isinstance(cfg, dict) and label not in ("models", "endpoint"):
                specs.extend(_specs_from_section(label, cfg))
        profiles[profile] = specs
    return profiles


def create_provider(spec: ModelSpec) -> Provider | None:
    """Instantiate the adapter for one spec; None if its key is missing."""
    from .adapters import (
        HuggingFaceProvider,
        LlamaCppProvider,
        OllamaProvider,
        OpenAIProvider,
    )

    provider = canonical_provider(spec.provider)
    if provider == "llama.cpp":
        return LlamaCppProvider(
            endpoint=spec.endpoint or "http://127.0.0.1:8830",
            model=spec.model,
        )
    if provider == "ollama":
        return OllamaProvider(
            endpoint=spec.endpoint or "http://localhost:11434/v1",
            model=spec.model,
        )
    if provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return None
        return OpenAIProvider(
            api_key=api_key,
            endpoint=spec.endpoint or "https://api.openai.com/v1",
            model=spec.model,
        )
    if provider == "anthropic":
        # Anthropic is driven through the OpenAI-compatible shim, as the
        # spine has always done (see git history of spine_cli.py).
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return None
        return OpenAIProvider(
            api_key=api_key,
            endpoint=spec.endpoint or "https://api.anthropic.com/v1",
            model=spec.model,
        )
    if provider == "huggingface":
        return HuggingFaceProvider(
            endpoint=spec.endpoint
            or "https://api-inference.huggingface.co/v1/chat/completions",
            model=spec.model,
            api_key=os.environ.get("HF_API_KEY", ""),
        )
    return None


def build_provider_map(
    profile: str,
    providers_data: dict[str, Any],
) -> dict[str, Provider]:
    """Instantiate every provider a profile declares, keyed by adapter name."""
    specs_by_profile = parse_provider_specs(providers_data)
    result: dict[str, Provider] = {}
    for spec in specs_by_profile.get(profile, []):
        instance = create_provider(spec)
        if instance is not None and instance.name not in result:
            result[instance.name] = instance
    return result


def select_for_task(
    rules: list[RouterRule], task: str
) -> RouterRule | None:
    """Resolve the routing rule for a task kind (exact match)."""
    for rule in rules:
        if rule.matches(task):
            return rule
    return None
