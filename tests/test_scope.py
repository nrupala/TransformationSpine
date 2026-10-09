# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from spine.context import SCOPE_POLICIES, ContextScope


def test_scope_ordering_rank() -> None:
    """Durability ladder: TRANSIENT < SESSION < PROJECT < PERSISTENT."""
    assert ContextScope.TRANSIENT.rank == 0
    assert ContextScope.SESSION.rank == 1
    assert ContextScope.PROJECT.rank == 2
    assert ContextScope.PERSISTENT.rank == 3


def test_promotion_only_one_level() -> None:
    assert ContextScope.SESSION.can_promote_to(ContextScope.PROJECT)
    assert not ContextScope.SESSION.can_promote_to(ContextScope.PERSISTENT)
    assert not ContextScope.TRANSIENT.can_promote_to(ContextScope.PROJECT)


def test_demotion_only_one_level() -> None:
    assert ContextScope.PROJECT.can_demote_to(ContextScope.SESSION)
    assert not ContextScope.PROJECT.can_demote_to(ContextScope.TRANSIENT)
    assert ContextScope.SESSION.can_demote_to(ContextScope.TRANSIENT)
    assert ContextScope.PERSISTENT.can_demote_to(ContextScope.PROJECT)
    assert not ContextScope.PERSISTENT.can_demote_to(ContextScope.SESSION)


def test_policy_table_persistent_defaults() -> None:
    """PERSISTENT and PROJECT never expire; TRANSIENT/SESSION have TTL."""
    assert SCOPE_POLICIES[ContextScope.PERSISTENT].ttl is None
    assert SCOPE_POLICIES[ContextScope.PROJECT].ttl is None
    assert SCOPE_POLICIES[ContextScope.TRANSIENT].ttl is not None
    assert SCOPE_POLICIES[ContextScope.SESSION].ttl is not None
    assert not SCOPE_POLICIES[ContextScope.TRANSIENT].persists
    assert SCOPE_POLICIES[ContextScope.PROJECT].persists
