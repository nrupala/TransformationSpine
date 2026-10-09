"""ContextStore — the spine's memory manager.

Holds every ContextFact by scope, enforces expiry, and exposes the scoping
operations (promote / demote / consolidate) that make the context model obey
variable-like lifetimes. Multiple sessions, projects, and providers may share
one store; isolation is by scope + owner, not by process.

The store is intentionally deterministic and unit-testable: it is part of the
control plane, not the stochastic plant.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .context import SCOPE_POLICIES, ContextFact, ContextScope

_SCOPES_BY_RANK: list[ContextScope] = sorted(ContextScope, key=lambda s: s.rank)


def _fact_to_dict(fact: ContextFact) -> dict[str, Any]:
    return {
        "key": fact.key,
        "value": fact.value,
        "scope": fact.scope.value,
        "origin": fact.origin,
        "owner": fact.owner,
        "created_at": fact.created_at.isoformat(),
        "last_accessed": fact.last_accessed.isoformat(),
        "id": fact.id,
    }


def _fact_from_dict(data: dict[str, Any]) -> ContextFact:
    return ContextFact(
        key=data["key"],
        value=data.get("value"),
        scope=ContextScope(data["scope"]),
        origin=data.get("origin", ""),
        owner=data.get("owner", ""),
        created_at=datetime.fromisoformat(data["created_at"]),
        last_accessed=datetime.fromisoformat(data["last_accessed"]),
        id=data.get("id", ""),
    )


class ScopeViolationError(ValueError):
    """Raised when a promotion/demotion crosses more than one durability level."""


class ContextStore:
    """Registry of scoped facts with lifecycle operations.

    Facts are keyed by (key, scope, owner); a fact may live at multiple scopes
    simultaneously (e.g. a decision demoted from PROJECT to SESSION while a
    PERSISTENT derived summary remains).
    """

    def __init__(self, path: str | Path | None = None) -> None:
        """Create a store.

        ``path`` is an optional durable backing file. When given (or when
        the SPINE_CONTEXT_PATH env var is set), facts in scopes whose
        policy persists (SESSION, PROJECT, PERSISTENT) are written through
        to that file on every mutation and reloaded on construction, so
        they survive process restarts. TRANSIENT facts are never written.
        Durable facts should carry JSON-serializable values; other values
        are stored via ``str()`` fallback and reload as strings.
        With no path, the store is purely in-memory (the historical
        behavior, still what most unit tests want).
        """
        self._facts: dict[tuple[str, ContextScope, str], ContextFact] = {}
        self._session_open: set[str] = set()
        if path is None:
            env_path = os.environ.get("SPINE_CONTEXT_PATH")
            path = Path(env_path) if env_path else None
        self._path: Path | None = Path(path) if path is not None else None
        if self._path is not None:
            self._load()

    # -- Durable backing ----------------------------------------------------

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        data = json.loads(self._path.read_text(encoding="utf-8"))
        for item in data.get("facts", []):
            fact = _fact_from_dict(item)
            self._facts[(fact.key, fact.scope, fact.owner)] = fact

    def _save(self) -> None:
        if self._path is None:
            return
        facts = [
            _fact_to_dict(f)
            for f in self._facts.values()
            if SCOPE_POLICIES[f.scope].persists
        ]
        payload = json.dumps({"facts": facts}, indent=1, default=str)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(self._path)  # atomic rename: no torn writes

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
            self._save()
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
        self._save()
        return fact

    # -- Lifecycle -------------------------------------------------------------

    def promote(self, fact: ContextFact, owner: str = "") -> ContextFact:
        """Create a hardened successor one durability level up.

        Promotion is the spine's explicit act of *hardening* knowledge:
        a fact proven by passing tests (SESSION) becomes a durable decision
        (PROJECT). Only one level per call — crossing two levels would
        shortcut the governance review that promotion implies.

        Semantics (by design, and tested): the successor *coexists* with
        the original, which remains at its own scope until consolidation
        or retirement removes it — the same fact may legitimately live at
        several scopes. Provenance is preserved: the successor keeps the
        original's origin chain (with this transition appended) and its
        original creation time, rather than appearing from nowhere.
        """
        if fact.scope is ContextScope.PERSISTENT or not fact.scope.can_promote_to(
            _SCOPES_BY_RANK[fact.scope.rank + 1]
        ):
            raise ScopeViolationError(
                f"Cannot promote {fact.scope.value} to a higher scope"
            )
        target = _SCOPES_BY_RANK[fact.scope.rank + 1]
        transition = f"promoted_from:{fact.scope.value}"
        promoted = ContextFact(
            key=fact.key,
            value=fact.value,
            scope=target,
            origin=f"{fact.origin}|{transition}" if fact.origin else transition,
            owner=owner or fact.owner,
            created_at=fact.created_at,
        )
        self._facts[(promoted.key, target, promoted.owner)] = promoted
        self._save()
        return promoted

    def demote(self, fact: ContextFact, owner: str = "") -> ContextFact:
        """Create a successor one durability level down (PROJECT -> SESSION).

        Demotion marks knowledge as *no longer authoritative* without
        deleting it; history remains in the decision log, and the fact may
        still be consulted at the lower scope. Like promote(), the
        successor coexists with the original and preserves its provenance
        chain and creation time.
        """
        if fact.scope.rank <= ContextScope.TRANSIENT.rank:
            raise ScopeViolationError("Cannot demote below TRANSIENT")
        target = _SCOPES_BY_RANK[fact.scope.rank - 1]
        transition = f"demoted_from:{fact.scope.value}"
        demoted = ContextFact(
            key=fact.key,
            value=fact.value,
            scope=target,
            origin=f"{fact.origin}|{transition}" if fact.origin else transition,
            owner=owner or fact.owner,
            created_at=fact.created_at,
        )
        self._facts[(demoted.key, target, demoted.owner)] = demoted
        self._save()
        return demoted

    def expire(self, key: str, scope: ContextScope, owner: str = "") -> None:
        """Remove a fact outright (the store-local equivalent of retirement)."""
        self._facts.pop((key, scope, owner), None)
        self._save()

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
        self._save()
        return promoted_count

    def compact_session(
        self, session_id: str, summary_text: str
    ) -> ContextFact | None:
        """Fold a session's facts into one compaction-checkpoint summary.

        The checkpoint pattern from the Token-Efficiency Engine (MyMilo
        checkpoint v2): long session history is *replaced* by a summary
        fact that carries its coverage — how many facts it folds and the
        earliest fact time it covers — so nothing is unrecoverable and
        the summary tier in context assembly can state what it stands
        for. Returns the summary fact, or None when the session held no
        facts. The summary fact is SESSION-scoped and owned by the
        session, so it persists (per scope policy) while the session is
        open and is itself folded by consolidate_session at close.
        """
        facts = [
            f
            for f in self._facts.values()
            if f.scope is ContextScope.SESSION and f.owner == session_id
        ]
        if not facts:
            return None
        covered_from = min(f.created_at for f in facts)
        for fact in facts:
            self._facts.pop((fact.key, ContextScope.SESSION, session_id), None)
        summary = ContextFact(
            key=f"session-summary:{session_id}",
            value=summary_text,
            scope=ContextScope.SESSION,
            origin=(
                f"compacted:{len(facts)}:from:{covered_from.isoformat()}"
            ),
            owner=session_id,
        )
        self._facts[(summary.key, ContextScope.SESSION, session_id)] = summary
        self._save()
        return summary

    def session_summary(self, session_id: str) -> ContextFact | None:
        """Return the session's compaction-checkpoint fact, if any."""
        return self._facts.get(
            (f"session-summary:{session_id}", ContextScope.SESSION, session_id)
        )

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
        if stale:
            self._save()

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
