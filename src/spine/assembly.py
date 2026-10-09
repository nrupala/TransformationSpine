"""Two-tier context assembly — CSA/HCA behavior at the engine layer.

From the Token-Efficiency Engine spec (live in MyMilo since v0.36.0):
every prompt's context is assembled in cache-stable order, so the
prefix a backend caches stays byte-identical across turns:

1. **Stable prefix** — PERSISTENT + PROJECT facts, deterministic order.
   This is the spine's standing context; it is never reordered by what
   the current query happens to be.
2. **Summary tier (HCA analog)** — the session's compaction-checkpoint
   summary under a hard budget (default 1024 tokens), headed by its
   coverage line so the model knows what the summary replaces.
3. **Retrieval tier (CSA analog)** — top-k (k<=8) SESSION/TRANSIENT
   facts scored by token-overlap relevance to the query, each capped
   (default 256 tokens), tier capped (default 2048 tokens).
4. **Recent remainder** — any remaining in-scope facts, newest first,
   filling whatever budget is left. Irrelevant history is dropped by
   budget, not by hope.

The assembly reports exactly what it used and dropped, so token spend
per turn is auditable from the CTST telemetry.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .context import ContextFact, ContextScope
from .tokenplan import estimate_tokens

SUMMARY_BUDGET = 1024
RETRIEVAL_BUDGET = 2048
RETRIEVAL_ITEM_CAP = 256
RETRIEVAL_TOP_K = 8


@dataclass
class Assembly:
    """The outcome of assembling context for one prompt."""

    text: str
    estimated_tokens: int
    facts_used: list[str] = field(default_factory=list)
    facts_dropped: list[str] = field(default_factory=list)
    summary_tokens: int = 0
    retrieval_tokens: int = 0


def _render(fact: ContextFact) -> str:
    origin = fact.origin or "unknown"
    return f"# {fact.key} [{fact.scope.value}] (origin: {origin})\n{fact.value}"


def _truncate_to_tokens(text: str, budget: int) -> str:
    """Crude but deterministic truncation to a token budget."""
    if estimate_tokens(text) <= budget:
        return text
    # ~4 chars per token in the estimator; keep whole lines where possible.
    limit = max(0, budget * 4 - 8)
    cut = text[:limit]
    return cut.rsplit("\n", 1)[0] if "\n" in cut else cut


def _relevance(fact: ContextFact, query_tokens: set[str]) -> float:
    tokens = set(f"{fact.key} {fact.value}".lower().split())
    if not tokens or not query_tokens:
        return 0.0
    return len(tokens & query_tokens) / len(tokens | query_tokens)


def assemble_context(
    facts: list[ContextFact],
    *,
    query: str = "",
    summary: str | None = None,
    summary_covers: int = 0,
    budget_tokens: int = 6144,
    summary_budget: int = SUMMARY_BUDGET,
    retrieval_budget: int = RETRIEVAL_BUDGET,
) -> Assembly:
    """Assemble in-scope ``facts`` into a cache-stable prompt block.

    ``budget_tokens`` is the total input budget for the context block
    (the caller derives it from the route plan). Facts that do not fit
    are reported in ``facts_dropped`` — never silently vanished.
    """
    used: list[str] = []
    dropped: list[str] = []
    spent = 0
    parts: list[str] = []

    # Tier 1 — stable prefix: durable facts, deterministic (key) order.
    remainder: list[ContextFact] = []
    for fact in sorted(facts, key=lambda f: f.key):
        if fact.scope in (ContextScope.PERSISTENT, ContextScope.PROJECT):
            rendered = _render(fact)
            cost = estimate_tokens(rendered)
            if spent + cost <= budget_tokens:
                parts.append(rendered)
                used.append(fact.key)
                spent += cost
            else:
                dropped.append(fact.key)
        else:
            remainder.append(fact)

    # Tier 2 — summary (HCA analog), hard-capped.
    summary_tokens = 0
    if summary:
        header = f"# session-summary (covers {summary_covers} facts)"
        body = _truncate_to_tokens(summary, summary_budget)
        block = f"{header}\n{body}"
        cost = estimate_tokens(block)
        if spent + cost <= budget_tokens:
            parts.append(block)
            summary_tokens = cost
            spent += cost

    # Tier 3 — retrieval (CSA analog): relevance-ranked, per-item + tier caps.
    query_tokens = set(query.lower().split())
    ranked = sorted(
        remainder,
        key=lambda f: (-_relevance(f, query_tokens), f.key),
    )
    retrieval_tokens = 0
    picked: list[ContextFact] = []
    for fact in ranked[:RETRIEVAL_TOP_K]:
        rendered = _truncate_to_tokens(_render(fact), RETRIEVAL_ITEM_CAP)
        cost = estimate_tokens(rendered)
        if (
            retrieval_tokens + cost <= retrieval_budget
            and spent + cost <= budget_tokens
        ):
            parts.append(rendered)
            used.append(fact.key)
            picked.append(fact)
            retrieval_tokens += cost
            spent += cost

    # Tier 4 — recent remainder, newest first, until the budget is spent.
    leftovers = sorted(
        (f for f in remainder if f not in picked),
        key=lambda f: f.created_at,
        reverse=True,
    )
    for fact in leftovers:
        rendered = _render(fact)
        cost = estimate_tokens(rendered)
        if spent + cost <= budget_tokens:
            parts.append(rendered)
            used.append(fact.key)
            spent += cost
        else:
            dropped.append(fact.key)

    text = "\n\n".join(parts)
    return Assembly(
        text=text,
        estimated_tokens=estimate_tokens(text) if text else 0,
        facts_used=used,
        facts_dropped=dropped,
        summary_tokens=summary_tokens,
        retrieval_tokens=retrieval_tokens,
    )
