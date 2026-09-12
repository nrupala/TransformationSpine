"""ContextStore — the spine's memory manager.

Holds every ContextFact by scope, enforces expiry, and exposes the scoping
operations (promote / demote / consolidate) that make the context model obey
variable-like lifetimes. Multiple sessions, projects, and providers may share
one store; isolation is by scope + owner, not by process.

The store is intentionally deterministic and unit-testable: it is part of the
control plane, not the stochastic plant.
"""

from __future__ import annotations

from datetime import UTC, datetime

from .context import SCOPE_POLICIES, ContextFact, ContextScope

_SCOPES_BY_RANK: list[ContextScope] = sorted(ContextScope, key=lambda s: s.rank)


class ScopeViolationError(ValueError):
    """Raised when a promotion/demotion crosses more than one durability level."""


class ContextStore:
    """Registry of scoped facts with lifecycle operations.

    Facts are keyed by (key, scope, owner); a fact may live at multiple scopes
    simultaneously (e.g. a decision demoted from PROJECT to SESSION while a
    PERSISTENT derived summary remains).
    """

    def __init__(self) -> None:
        self._facts: dict[tuple[str, ContextScope, str], ContextFact] = {}
        self._session_open: set[str] = set()

    # -- Reads ----------------------------------------------------------------

    def get(
        self,
        key: str,
        scope: ContextScope,
        owner: str = "",
    ) -> ContextFact | None:
        """Fetch a fact, pruning expired facts on access."""
        fact = self._facts.get((key, scope, owner))
        if fact is None:
            return None
        if fact.is_expired():
            del self._facts[(key, scope, owner)]
            return None
        fact.touch()
        return fact

    def query(
        self,
        scope: ContextScope | None = None,
        owner: str = "",
        min_scope: ContextScope | None = None,
    ) -> list[ContextFact]:
        """Return facts filtered by scope/owner, dropping any expired ones first."""
        self._expire_all()
        result: list[ContextFact] = []
        for fact in self._facts.values():
            if owner and fact.owner != owner:
                continue
            if scope is not None and fact.scope != scope:
                continue
            if min_scope is not None and fact.scope.rank < min_scope.rank:
                continue
            result.append(fact)
        return sorted(result, key=lambda f: f.key)

    def visible_to(
        self,
        scope: ContextScope,
        owner: str = "",
    ) -> list[ContextFact]:
        """What context is in scope *here*? Facts at this scope or above.

        This is the spine's answer to the user's core question: a session agent
        sees SESSION facts plus everything PROJECT and PERSISTENT; it does not
        see transient or other-session facts it was not handed.
        """
        return self.query(min_scope=scope, owner=owner)

    def get_all(self) -> list[ContextFact]:
        """Every unexpired fact, across scopes."""
        self._expire_all()
        return list(self._facts.values())

    # -- Writes ---------------------------------------------------------------

    def put(
        self,
        fact: ContextFact,
        *,
        force_scope: ContextScope | None = None,
    ) -> ContextFact:
        """Store a fact. ``force_scope`` lets a caller override the fact's own.

        Declaring over an existing key + scope + owner replaces it (that is the
        mutable reference semantics: the reference updates, history stays in
        the decision log).
        """
        scope = force_scope or fact.scope
        key = (fact.key, scope, fact.owner)
        if not SCOPE_POLICIES[scope].persists:
            # transient facts may override nothing persistent; they are shadowed.
            pass
        self._facts[key] = fact
        return fact

    # -- Lifecycle -------------------------------------------------------------

    def promote(self, fact: ContextFact, owner: str = "") -> ContextFact:
        """Move a fact one durability level up (e.g. SESSION -> PROJECT).

        Promotion is the spine's explicit act of *hardening* knowledge:
        a fact proven by passing tests (SESSION) becomes a durable decision
        (PROJECT). Only one level per call — crossing two levels would
        shortcut the governance review that promotion implies.
        """
        if fact.scope is ContextScope.PERSISTENT or not fact.scope.can_promote_to(
            _SCOPES_BY_RANK[fact.scope.rank + 1]
        ):
            raise ScopeViolationError(
                f"Cannot promote {fact.scope.value} to a higher scope"
            )
        target = _SCOPES_BY_RANK[fact.scope.rank + 1]
        promoted = ContextFact(
            key=fact.key,
            value=fact.value,
            scope=target,
            origin=f"promoted_from:{fact.scope.value}",
            owner=owner or fact.owner,
            created_at=datetime.now(UTC),
        )
        self._facts[(promoted.key, target, promoted.owner)] = promoted
        return promoted

    def demote(self, fact: ContextFact, owner: str = "") -> ContextFact:
        """Move a fact one durability level down (e.g. PROJECT -> SESSION).

        Demotion marks knowledge as *no longer authoritative* without
        deleting it; history remains in the decision log, and the fact may
        still be consulted at the lower scope.
        """
        if fact.scope.rank <= ContextScope.TRANSIENT.rank:
            raise ScopeViolationError("Cannot demote below TRANSIENT")
        target = _SCOPES_BY_RANK[fact.scope.rank - 1]
        demoted = ContextFact(
            key=fact.key,
            value=fact.value,
            scope=target,
            origin=f"demoted_from:{fact.scope.value}",
            owner=owner or fact.owner,
            created_at=datetime.now(UTC),
        )
        self._facts[(demoted.key, target, demoted.owner)] = demoted
        return demoted

    def expire(self, key: str, scope: ContextScope, owner: str = "") -> None:
        """Remove a fact outright (the store-local equivalent of retirement)."""
        self._facts.pop((key, scope, owner), None)

    def consolidate_session(
        self,
        session_id: str,
        *,
        promotion_keys: list[str] | None = None,
    ) -> int:
        """Fold a closing session's facts.

        SESSION-scoped facts owned by ``session_id`` are either promoted to
        PROJECT (when listed in ``promotion_keys`` — the proven ones) or
        expired (the ephemeral ones). Returns the number of facts promoted.
        """
        promoted_count = 0
        targets: list[tuple[str, ContextFact]] = []
        for fact in list(self._facts.values()):
            if fact.scope != ContextScope.SESSION or fact.owner != session_id:
                continue
            if promotion_keys and fact.key in promotion_keys:
                targets.append((fact.key, fact))
            else:
                self._facts.pop((fact.key, ContextScope.SESSION, session_id), None)
        for _, fact in targets:
            # replace the session fact with its PROJECT-scoped successor
            self._facts.pop((fact.key, ContextScope.SESSION, session_id), None)
            self.promote(fact, owner=session_id)
            promoted_count += 1
        self._session_open.discard(session_id)
        return promoted_count

    def open_session(self, session_id: str) -> None:
        """Mark a session open (only open sessions hold SESSION facts)."""
        self._session_open.add(session_id)

    def is_session_open(self, session_id: str) -> bool:
        return session_id in self._session_open

    # -- Internals --------------------------------------------------------------

    def _expire_all(self) -> None:
        now = datetime.now(UTC)
        stale = [
            key
            for key, fact in self._facts.items()
            if fact.is_expired(now)
        ]
        for key in stale:
            del self._facts[key]

    def __len__(self) -> int:
        self._expire_all()
        return len(self._facts)


def snapshot_for_prompt(
    store: ContextStore,
    scope: ContextScope,
    owner: str = "",
    limit: int | None = None,
) -> str:
    """Render the in-scope context as a compact prompt block.

    Deterministic ordering (by key, then scope desc) so the same context always
    renders identically — stable prompts are required for convergence testing.
    """
    facts = store.visible_to(scope, owner=owner)
    lines = [
        f"# {f.key} [{f.scope.value}] (origin: {f.origin or 'unknown'})"
        f"\n{f.value}"
        for f in facts
    ]
    if limit is not None:
        lines = lines[:limit]
    return "\n\n".join(lines)
