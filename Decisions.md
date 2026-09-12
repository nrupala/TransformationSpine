# Architecture Decisions

---

## ADR-001

Decision:
Provider Neutral Architecture

Status:
Accepted

Reason:

Avoid dependency on any single model vendor.

Alternatives:

- OpenAI only
- Anthropic only

Tradeoffs:

More complexity
Lower lock-in

Revisit:

When market standard emerges.

---

## ADR-002

Decision:

Externalized Memory

Status:

Accepted

Reason:

Context should survive platform migration.