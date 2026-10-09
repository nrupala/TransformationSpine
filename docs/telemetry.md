# Telemetry

Telemetry answers three questions per provider: how much did it cost
(tokens, latency), and did the work converge (error signal)?

## Where it comes from

1. Adapters report `usage` on every `ProviderResult`.
2. `ProviderResult` derives its `telemetry` dict from usage at
   construction — a result with usage can never have empty telemetry.
3. The gated cycle (`src/spine/api.py`) measures latency, computes the
   authoritative error signal via `spine.gates`, and appends a CTST
   record for **every** cycle — committed or not — carrying:
   `error_signal`, `committed`, `outcome`, `assessment` (verdict +
   gate checks), and `telemetry` (tokens, `latency_ms`, the token
   plan: estimated input, planned max tokens, context window, and the
   count of tool executions).

## Reading it

- `GET /api/v1/telemetry` — per-provider averages (token averages over
  the records that carry them; `avg_error_signal` over all runs) and
  run counts, aggregated from the CTST ledger.
- `GET /api/v1/ledger` — the raw records for today.
- `GET /api/v1/ledger/verify` — hash-chain verification of the ledger
  the telemetry was aggregated from.
- `spine telemetry` (CLI) — the same aggregation in the terminal.

## Honesty rules

- Averages divide by the number of values actually present, never by
  run count.
- `avg_error_signal` reads the record's own `error_signal` field (set
  by the gates), not a copy inside telemetry.
- If the ledger is empty, the endpoint returns empty providers and a
  zero total — it does not fabricate zeros per provider.
