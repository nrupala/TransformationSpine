<!-- Copyright 2026 Nrupal Akolkar -->
<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# Serving surfaces — agents, humans, programs

TransformationSpine serves every kind of caller through the same
gated cycle (same planner, gates, CTST ledger, telemetry). Pick the
surface that fits the caller:

## Agents

- **MCP** — `POST /mcp` (Streamable HTTP, stateless JSON-RPC) or
  `spine mcp` (stdio, for subprocess-style agent hosts). Tools:
  `spine_transform`, `spine_status`, `spine_context`,
  `spine_ledger_verify`, `spine_connector_execute`, one tool per
  connector capability (`<connector>__<tool>`), built-in tools.
- **A2A** — discovery at `GET /.well-known/agent-card.json`;
  JSON-RPC at `POST /a2a` (`message/send`, `tasks/get`). A message's
  text becomes a transform intent; the completed Task carries the
  cycle's output as an artifact plus verdict metadata. Provider and
  scope travel in message metadata.
- **ACP** — REST: `GET /acp/agents` (manifest),
  `POST /acp/agents/{name}/runs` with `{"input": "...", "provider": ...}`
  (ACP-style message parts also accepted), `GET .../runs/{id}`.

## Humans

- **Browser UI** — `GET /ui`: one self-contained page (status,
  transform form, ledger verify, connector list) over the REST API.
- **CLI** — `spine status|transform|context|ledger|telemetry|
  providers|connector|workflow|mcp`.

## Programs

- **REST API** — `/api/v1/*` (status, transform, context, ledger,
  ledger/verify, telemetry, connectors + execute).
- **Python API** — `import spine`: ContextStore, CTSTLedger,
  ConnectorRegistry, evaluate_result, plan_max_tokens, and the rest
  of the public exports in `spine/__init__.py`.
