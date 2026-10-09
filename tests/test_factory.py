"""Provider factory / profile routing tests (audit F-06).

Before the fix: Providers.yaml's nested cloud/hybrid sections were
silently dropped by the parser, the CLI loaded nothing for any profile,
and the API never read the YAMLs at all. These tests parse the repo's
real Providers.yaml / Routing.yaml and prove profiles now select.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from spine.factory import (
    build_provider_map,
    parse_provider_specs,
    select_for_task,
)
from spine.provider import ModelSpec, RouterRule

ROOT = Path(__file__).resolve().parent.parent


def _providers_data() -> dict:
    return yaml.safe_load((ROOT / "Providers.yaml").read_text())


def _routing_data() -> dict:
    return yaml.safe_load((ROOT / "Routing.yaml").read_text())


def test_parser_drops_nothing() -> None:
    by_profile = parse_provider_specs(_providers_data())
    assert set(by_profile) == {"local", "cloud", "hybrid"}
    cloud_providers = {s.provider for s in by_profile["cloud"]}
    assert {"openai", "anthropic", "huggingface"} <= cloud_providers
    # from_yaml (all profiles flattened) now sees the cloud models too
    all_specs = ModelSpec.from_yaml(_providers_data())
    models = {s.model for s in all_specs}
    assert "gpt-5" in models
    assert "Qwen3.5-9B-Q8_0" in models


def test_local_profile_builds_llama() -> None:
    providers = build_provider_map("local", _providers_data())
    assert set(providers) == {"llama.cpp"}
    assert providers["llama.cpp"].model == "Qwen3.5-9B-Q8_0"


def test_cloud_profile_skips_keyless(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    providers = build_provider_map("cloud", _providers_data())
    assert "openai" not in providers
    assert "anthropic" not in providers
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    providers = build_provider_map("cloud", _providers_data())
    assert "openai" in providers


def test_routing_selects_cloud_primary() -> None:
    rules = RouterRule.from_yaml(_routing_data(), profile="cloud")
    rule = select_for_task(rules, "coding")
    assert rule is not None
    assert rule.primary_provider == "anthropic"
    local_rules = RouterRule.from_yaml(_routing_data(), profile="local")
    local_rule = select_for_task(local_rules, "coding")
    assert local_rule is not None
    assert local_rule.primary_provider == "llama.cpp"


def test_cli_provider_list_uses_profile() -> None:
    env = {"PATH": "/usr/bin:/bin", "HOME": str(Path.home())}
    out = subprocess.run(
        [sys.executable, "spine_cli.py", "provider", "list"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert "llama.cpp" in out.stdout
