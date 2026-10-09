# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: Apache-2.0
"""Context lifecycle scoping — the transformation spine's core data model.

Context is contextual to its usage. This module formalizes that insight as an
explicit scoping model (mirroring variable lifetime rules in compiled
languages), so the spine can always answer ``what context is in scope here?``
without ambiguity.

Scopes, by increasing durability and decreasing volatility:

* ``TRANSIENT``  — lives for the duration of a single inference call / request.
                  Analogy: temporaries on the stack. Never persisted.
* ``SESSION``    — lives for one agent/coding session (a test run, a task
                  dispatch). Analogy: stack frames. Persisted while the
                  session is open, consolidated or dropped at close.
* ``PROJECT``    — lives across the project lifecycle (a feature, a milestone,
                  a decision that must survive). Analogy: module-level state.
                  Persisted for as long as the owning artifact exists.
* ``PERSISTENT`` — built into the code / config itself; survives every
                  migration and session. Analogy: global constants washed into
                  the binary. Never expires on its own.

Promotion/demotion between scopes is the spine's job: a fact proven by a test
may be promoted SESSION -> PROJECT; a superseded decision may be demoted
PROJECT -> SESSION and then retired.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
from uuid import uuid4


class ContextScope(Enum):
    """Durability levels for context. Higher = longer-lived, more durable."""

    TRANSIENT = "transient"
    SESSION = "session"
    PROJECT = "project"
    PERSISTENT = "persistent"

    @property
    def rank(self) -> int:
        """Numeric ordering: used for legality of promote()/demote()."""
        return {
            ContextScope.TRANSIENT: 0,
            ContextScope.SESSION: 1,
            ContextScope.PROJECT: 2,
            ContextScope.PERSISTENT: 3,
        }[self]

    def can_promote_to(self, target: ContextScope) -> bool:
        """A scope may only be promoted to the next durability level up."""
        return self.rank + 1 == target.rank

    def can_demote_to(self, target: ContextScope) -> bool:
        """A scope may only be demoted to the next durability level down."""
        return self.rank - 1 == target.rank


@dataclass(frozen=True)
class ScopePolicy:
    """Rules for a scope: when it expires, who may hold it, whether it persists."""

    scope: ContextScope
    ttl: timedelta | None = None
    persists: bool = False
    consolidate_on_close: bool = True


# Policy table — the spine's built-in constants. These are PERSISTENT facts.
SCOPE_POLICIES: dict[ContextScope, ScopePolicy] = {
    ContextScope.TRANSIENT: ScopePolicy(
        scope=ContextScope.TRANSIENT,
        ttl=timedelta(minutes=10),
        persists=False,
    ),
    ContextScope.SESSION: ScopePolicy(
        scope=ContextScope.SESSION,
        ttl=timedelta(hours=8),
        persists=True,
        consolidate_on_close=True,
    ),
    ContextScope.PROJECT: ScopePolicy(
        scope=ContextScope.PROJECT,
        ttl=None,
        persists=True,
    ),
    ContextScope.PERSISTENT: ScopePolicy(
        scope=ContextScope.PERSISTENT,
        ttl=None,
        persists=True,
    ),
}


@dataclass
class ContextFact:
    """A single scoped datum in the spine.

    ``provenance`` records where the fact came from (session id, provider,
    decision id), matching the OCS lineage principle: a fact without a source
    is not a fact worth trusting.
    """

    key: str
    value: Any
    scope: ContextScope
    origin: str = ""
    owner: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_accessed: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: str = field(default_factory=lambda: str(uuid4()))

    def is_expired(self, now: datetime | None = None) -> bool:
        """True when the fact has outlived its scope policy TTL."""
        now = now or datetime.now(UTC)
        ttl = SCOPE_POLICIES[self.scope].ttl
        if ttl is None:
            return False
        return now - self.created_at > ttl

    def touch(self, now: datetime | None = None) -> None:
        """Refresh last-accessed (may keep a SESSION scope alive a little longer)."""
        self.last_accessed = now or datetime.now(UTC)


def declare(
    key: str,
    value: Any,
    scope: ContextScope,
    origin: str = "",
    owner: str = "",
) -> ContextFact:
    """Declare a fact in the given scope — the spine equivalent of a ``let``."""
    return ContextFact(
        key=key,
        value=value,
        scope=scope,
        origin=origin,
        owner=owner,
    )
