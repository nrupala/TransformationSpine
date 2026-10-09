# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
"""ContextStore durable-backing tests (audit F-14 regression suite).

Before the fix the store was a pure in-memory dict: facts in scopes the
README marks "Persisted: yes" vanished on process restart. These tests
prove survival across store instances sharing one backing file, and that
TRANSIENT facts are never written to disk.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from spine.context import ContextScope, declare
from spine.store import ContextStore


def test_project_and_persistent_facts_survive_restart(tmp_path: Path) -> None:
    path = tmp_path / "ctx.json"
    store = ContextStore(path=path)
    store.put(declare("decision.adr-001", "provider neutral", ContextScope.PROJECT))
    store.put(declare("brand.voice", "plain", ContextScope.PERSISTENT))
    store.put(declare("scratch", "temp", ContextScope.TRANSIENT))

    reopened = ContextStore(path=path)
    got = reopened.get("decision.adr-001", ContextScope.PROJECT)
    assert got is not None and got.value == "provider neutral"
    got2 = reopened.get("brand.voice", ContextScope.PERSISTENT)
    assert got2 is not None and got2.value == "plain"
    # TRANSIENT facts are never persisted.
    assert reopened.get("scratch", ContextScope.TRANSIENT) is None
    raw = json.loads(path.read_text())
    assert all(item["scope"] != "transient" for item in raw["facts"])


def test_promotion_is_persisted(tmp_path: Path) -> None:
    path = tmp_path / "ctx.json"
    store = ContextStore(path=path)
    fact = declare("proven.result", "tests green", ContextScope.SESSION, owner="s1")
    store.put(fact)
    store.promote(fact, owner="s1")

    reopened = ContextStore(path=path)
    got = reopened.get("proven.result", ContextScope.PROJECT, "s1")
    assert got is not None and got.value == "tests green"


def test_expire_removes_from_disk(tmp_path: Path) -> None:
    path = tmp_path / "ctx.json"
    store = ContextStore(path=path)
    store.put(declare("k", "v", ContextScope.PROJECT))
    store.expire("k", ContextScope.PROJECT)

    reopened = ContextStore(path=path)
    assert reopened.get("k", ContextScope.PROJECT) is None


def test_env_var_selects_backing_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "env-ctx.json"
    monkeypatch.setenv("SPINE_CONTEXT_PATH", str(path))
    store = ContextStore()
    store.put(declare("k", "v", ContextScope.PROJECT))
    assert path.exists()
    assert ContextStore().get("k", ContextScope.PROJECT) is not None
