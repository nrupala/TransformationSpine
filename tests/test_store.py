from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from spine.context import ContextFact, ContextScope, declare
from spine.store import ContextStore, ScopeViolationError, snapshot_for_prompt


def _fact(key: str, value: str, scope: ContextScope, owner: str = "") -> ContextFact:
    return declare(key, value, scope, origin=f"test:{key}", owner=owner)


def test_put_and_get_roundtrip() -> None:
    store = ContextStore()
    fact = _fact("decision.adr-001", "provider neutral", ContextScope.PROJECT)
    store.put(fact)
    got = store.get("decision.adr-001", ContextScope.PROJECT)
    assert got is not None
    assert got.value == "provider neutral"


def test_visible_to_scopes_upward() -> None:
    store = ContextStore()
    store.put(_fact("k1", "v1", ContextScope.PERSISTENT))
    store.put(_fact("k2", "v2", ContextScope.PROJECT))
    store.put(_fact("k3", "v3", ContextScope.SESSION))
    store.put(_fact("k4", "v4", ContextScope.TRANSIENT))

    # An agent in SESSION scope sees SESSION + PROJECT + PERSISTENT, not TRANSIENT.
    visible = store.visible_to(ContextScope.SESSION)
    keys = {f.key for f in visible}
    assert {"k1", "k2", "k3"} <= keys
    assert "k4" not in keys


def test_promotion_moves_one_level_and_hardens() -> None:
    store = ContextStore()
    fact = _fact("proven.result", "tests green", ContextScope.SESSION, owner="s1")
    store.put(fact)
    promoted = store.promote(fact, owner="s1")
    assert promoted.scope is ContextScope.PROJECT
    assert promoted.origin == "promoted_from:session"
    # original session fact still exists until consolidated
    assert store.get("proven.result", ContextScope.SESSION, "s1") is not None


def test_promote_top_scope_is_forbidden() -> None:
    store = ContextStore()
    fact = _fact("x", "y", ContextScope.PERSISTENT)
    with pytest.raises(ScopeViolationError):
        # PERSISTENT is the top of the ladder; nothing above it.
        store.promote(fact)


def test_promote_moves_exactly_one_level() -> None:
    store = ContextStore()
    fact = _fact("x", "y", ContextScope.TRANSIENT)
    promoted = store.promote(fact)
    assert promoted.scope is ContextScope.SESSION


def test_demote_lower_than_transient_is_forbidden() -> None:
    store = ContextStore()
    fact = _fact("x", "y", ContextScope.TRANSIENT)
    with pytest.raises(ScopeViolationError):
        store.demote(fact)


def test_consolidate_session_promotes_proven_and_drops_ephemeral() -> None:
    store = ContextStore()
    store.open_session("s1")
    store.put(_fact("proven", "kept", ContextScope.SESSION, owner="s1"))
    store.put(_fact("scratch", "drop", ContextScope.SESSION, owner="s1"))

    n = store.consolidate_session("s1", promotion_keys=["proven"])
    assert n == 1
    # proven promoted to PROJECT, scratch gone
    assert store.get("proven", ContextScope.PROJECT, "s1") is not None
    assert store.get("scratch", ContextScope.SESSION, "s1") is None


def test_expired_fact_is_pruned_on_read() -> None:
    store = ContextStore()
    old = datetime.now(UTC) - timedelta(hours=1)
    fact = _fact("stale", "x", ContextScope.TRANSIENT)
    fact.created_at = old  # TRANSIENT TTL is 10 minutes
    store.put(fact)
    assert store.get("stale", ContextScope.TRANSIENT) is None


def test_snapshot_is_deterministic() -> None:
    store = ContextStore()
    store.put(_fact("b", "2", ContextScope.PROJECT))
    store.put(_fact("a", "1", ContextScope.PERSISTENT))
    first = snapshot_for_prompt(store, ContextScope.SESSION)
    second = snapshot_for_prompt(store, ContextScope.SESSION)
    assert first == second
    # both facts present
    assert "a" in first and "b" in first
