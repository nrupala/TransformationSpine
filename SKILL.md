<!-- Copyright 2026 Nrupal Akolkar -->
<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->

# Skill: TransformationSpine — gated transformation cycles for agents

Use this skill when you are an AI agent and you need work done through
a **governed** cycle rather than a bare model call: the spine owns the
context, the memory, the decisions, and the record. Models are workers;
the spine assembles the minimum sufficient in-scope context, runs the
provider, evaluates the result against its gates, and writes the cycle
to a tamper-evident ledger (CTST, hash-chained).

## When to reach for the spine

- A transformation whose context must be scoped (TRANSIENT / SESSION /
  PROJECT / PERSISTENT), provenance-tracked, and auditable afterwards.
- Work on connected systems (GitHub, Jira, Azure DevOps, Confluence,
  Databricks, ServiceNow) that should pass through one governed door.
- Call a model directly instead when the task is one-shot, needs no
  memory, no decision record, and no audit trail — the spine's value
  is the governance around the call, not the call itself.

## Connect

- **Discovery:** `GET /.well-known/agent-card.json` (A2A agent card).
- **MCP (HTTP):** `POST /mcp` (Streamable HTTP, stateless JSON-RPC).
- **MCP (stdio):** `python spine_cli.py mcp` — for subprocess-style
  agent hosts.
- **A2A:** `POST /a2a` (`message/send`, `tasks/get`); the completed
  Task carries the cycle's output plus verdict metadata.

## The tools (MCP)

| Tool | Arguments | What it does |
|---|---|---|
| `spine_status` | — | Spine health, providers, ledger size, safeguards |
| `spine_context` | `scope` (default `SESSION`) | The context facts visible to a scope |
| `spine_transform` | `intent` (required), `provider`, `scope` | Run one gated transformation cycle |
| `spine_ledger_verify` | — | Verify the CTST ledger hash chain from disk |
| `spine_connector_execute` | `connector`, `tool`, `params` | Execute a tool on a discovered connector |
| `<connector>__<tool>` | per connector | One tool per connector capability |

## Workflow

1. **Check in first.** `spine_status` — confirm the spine is up, see
   which providers and connectors it actually has. An empty provider
   list means transforms cannot run yet; say so rather than retrying.
2. **Read the context you will be judged against.** `spine_context`
   for your scope. The spine's decisions and facts live there, not in
   your own memory of earlier calls.
3. **Transform.** `spine_transform` with a plain-language intent.
4. **Read the verdict, not just the output.** Every cycle reports its
   **error signal**: 0.0 means the result converged (all gates green);
   anything above 0 means it did **not** converge. Report a
   non-converged result as non-converged — never present it as a
   finished success.
5. **Verify the record when it matters.** `spine_ledger_verify`
   confirms the cycle you just ran is in the hash-chained ledger.

## Rules of the house

- Worker behaviour inside a cycle is governed by `AGENT_CONTRACT.md`
  in this repository: you do not own memory, decisions, or provider
  routing — read the spine first, never overwrite existing decisions,
  and record significant changes as ADR entries.
- Context is scoped and minimum-sufficient by design. Do not try to
  pull PERSISTENT context into a task that only earned SESSION scope.

---

*Agentic Packaging Standard conformance (2026-11-16): explicit
uncertainty — met (every cycle carries its error signal / convergence
verdict; this file's step 4 makes reading it a rule); composite task
tools — met in substance (`spine_transform` is the task-level call;
status/context/ledger tools are its probes); agent onboarding — met by
this file (+ `AGENT_CONTRACT.md` for in-cycle behaviour, the A2A agent
card for discovery); zero-compile install — open (not on PyPI,
releases carry no assets; the hosted demo at spine.aimlds.org is the
zero-install trial); measured traces — met in part (certification
package under `certification/`; no public benchmark trace);
terminal-story docs — met (README "Try it" shows real responses
captured from this release).*
