<!-- Copyright 2026 Nrupal Akolkar -->
<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# Workflows

Workflows are versionable DAGs (nodes + edges) defined in JSON or
YAML, renderable as Mermaid, and — since v0.2.0 — executable.

## Authoring

```bash
spine workflow init --name myflow        # writes myflow.json + myflow.mmd
```

Node types: `input`, `action` (requires `action`), `gate` (requires
`gate`), `output`. The standard template is:

```
input -> context (context.assemble) -> provider (provider.complete)
      -> verify (gate: error_signal == 0) -> commit (ledger.append) -> output
```

## Validation

`validate_workflow()` reports duplicate ids, unknown node types,
actions/gates missing their payloads, dangling edges (at parse time),
and **cycles** — execution order is a topological sort
(`topological_order()`), which raises on a cyclic graph.

## Execution

```bash
spine workflow run myflow.json --intent "summarize the change"
```

`execute_workflow(workflow, handlers, initial_state)` runs nodes in
topological order:

- Action nodes dispatch to `handlers[action]` — callables
  `(node, state) -> value`. `build_default_handlers(store, provider,
  ledger)` provides real handlers for the template's actions:
  context assembly from the store, provider completion (which
  publishes `error_signal` into state), and a real CTST ledger append
  returning the record hash.
- Gate nodes evaluate a small, safe expression subset —
  `<state-key> <op> <number>` with `== != < <= > >=` (no `eval`). A
  failed gate stops the run with status `gate_failed`: downstream
  nodes, including the commit, never run.
- The run returns a `WorkflowRun` (order, per-node outputs, status,
  failed node). With no reachable provider, the provider step reports
  `error_signal = 1.0` and the gate blocks the commit — the spine
  working as designed, not a simulated pass.
