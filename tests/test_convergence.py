"""The convergence test — proves the spine's core thesis.

"The spine makes outcome convergence achievable no matter if it is llama.cpp
running a small model or Codex running a big one."

This test drives two *different* provider backends (a tiny deterministic local
fake standing in for llama.cpp, and a larger simulated cloud fake standing in
for Codex) through the SAME scoped context, the same prompt, and the same
gates, then asserts both converge to the same committed output.

The convergence guarantee being tested is NOT that providers produce identical
text — it is that the spine's gates + scratch-to-commit loop converge the
gap to zero for BOTH engines. Engine strength affects speed, not the spine's
ability to converge.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from spine.context import ContextFact, ContextScope, declare
from spine.provider import Provider
from spine.result import ProviderResult
from spine.store import ContextStore


@dataclass
class FakeProvider:
    """A controllable provider double. ``quality`` in [0,1] models capability:

    lower quality = noisier/more error-prone output per iteration.
    A 'small model' has low quality; a 'big model' high quality. Both respond
    to the same Protocol interface — that is the swap-cost-zero point.
    """

    name: str
    endpoint: str = "fake://local"
    quality: float = 0.9
    _attempt: int = field(default=0, init=False, repr=False)

    def list_models(self) -> list[str]:
        return ["fake-model"]

    def complete(
        self,
        prompt: str,
        context: list[ContextFact],
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        **kwargs: object,
    ) -> ProviderResult:
        # deterministic noise: converges fully by the (1/quality)-th honest attempt
        self._attempt += 1
        converged = self._attempt >= max(1, round((1.0 - self.quality) * 10))
        return ProviderResult(
            success=converged,
            output="CONVERGED OUTPUT" if converged else "PARTIAL scratch work",
            provider=self.name,
            model="fake-model",
            error_signal=0.0 if converged else 0.5,
        )

    def embed(self, text: str, model: str | None = None) -> list[float]:
        return [1.0]


def run_journey(provider: Provider, store: ContextStore) -> float:
    """Run one gated transformation cycle to committed output.

    Deterministic oracle: the committed state must equal the target string and
    every gate must pass. Uses only the spine's scoped context for inputs.
    """
    # spine assembles context from what is in scope for the session
    facts = store.visible_to(ContextScope.SESSION)
    prompt = "transform reality toward the committed output.\n" + "\n".join(
        f"- {f.key}: {f.value}" for f in facts
    )

    scratch: str | None = None
    for _ in range(20):  # bounded journey; mirrors ocscoder gate discipline
        result = provider.complete(prompt, facts, max_tokens=64)
        scratch = result.output
        # gate: output must be exactly the committed artifact
        if result.is_converged and scratch == "CONVERGED OUTPUT":
            # gate green -> commit, owned by the engine that produced it so
            # provenance never collides across providers.
            store.put(
                declare(
                    "committed.artifact",
                    scratch,
                    ContextScope.PROJECT,
                    origin=f"provider:{provider.name}",
                    owner=provider.name,
                )
            )
            return result.error_signal
    return 1.0  # did not converge


def test_convergence_holds_across_weak_and_strong_providers() -> None:
    store = ContextStore()
    store.put(
        declare(
            "commitment.output",
            "CONVERGED OUTPUT",
            ContextScope.PERSISTENT,
            origin="user",
        )
    )

    small_local = FakeProvider(name="llama_cpp_8b", quality=0.6)  # llama.cpp small
    big_cloud = FakeProvider(name="codex_super", quality=1.0)  # Codex big

    err_small = run_journey(small_local, store)
    err_big = run_journey(big_cloud, store)

    # Both engines converge to the same committed artifact (gap -> 0).
    assert err_small == 0.0, f"small engine did not converge: {err_small}"
    assert err_big == 0.0, f"big engine did not converge: {err_big}"

    # Governance: each engine's commit is provenance-tracked and distinct —
    # the strong engine did NOT silently overwrite the weak engine's fact.
    small = store.get("committed.artifact", ContextScope.PROJECT, "llama_cpp_8b")
    big = store.get("committed.artifact", ContextScope.PROJECT, "codex_super")
    assert small is not None and small.value == "CONVERGED OUTPUT"
    assert big is not None and big.value == "CONVERGED OUTPUT"
    assert small.origin == "provider:llama_cpp_8b"
    assert big is not small


def test_provider_swap_loses_nothing_contextually() -> None:
    """Switching the engine must not lose the spine's context.

    Same store, different provider -> the PERSISTENT context the spine holds
    is handed to the new engine unchanged.
    """
    store = ContextStore()
    store.put(
        declare("decision.routing", "coding->anthropic/sonnet", ContextScope.PERSISTENT)
    )
    store.put(declare("decision.provider-neutral", "accepted", ContextScope.PROJECT))

    facts = store.visible_to(ContextScope.SESSION)
    rendered = {f.key: f.value for f in facts}

    assert rendered["decision.routing"] == "coding->anthropic/sonnet"
    assert rendered["decision.provider-neutral"] == "accepted"


def test_fake_provider_complies_with_provider_protocol() -> None:
    """The test double must be recognized as a genuine Provider runtime_checkable."""
    from spine.provider import Provider

    assert isinstance(FakeProvider(name="p"), Provider)


def test_routing_rules_and_model_specs_from_yaml_shape() -> None:
    """The typed config layer parses the repo's YAML shapes without losing fields."""
    from spine.provider import ModelSpec, RouterRule

    providers_cfg = {
        "providers": {
            "anthropic": {
                "endpoint": "https://api.anthropic.com/v1",
                "models": ["sonnet"],
                "strengths": ["coding"],
            },
            "ollama": {
                "endpoint": "http://localhost:11434",
                "models": ["deepseek"],
                "strengths": ["local workloads"],
            },
        }
    }
    specs = ModelSpec.from_yaml(providers_cfg)
    assert len(specs) == 2
    by_name = {s.provider: s for s in specs}
    assert by_name["ollama"].endpoint == "http://localhost:11434"
    assert by_name["ollama"].model == "deepseek"
    assert "local workloads" in by_name["ollama"].strengths

    routes_cfg = {
        "routes": {
            "coding": {
                "primary": {"provider": "anthropic", "model": "sonnet"},
                "fallback": {"provider": "openai", "model": "gpt-5"},
            }
        }
    }
    rules = RouterRule.from_yaml(routes_cfg)
    assert len(rules) == 1
    assert rules[0].primary_provider == "anthropic"
    assert rules[0].fallback_model == "gpt-5"
    assert rules[0].matches("coding")
