# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later

# Test Record — TransformationSpine v0.3.0

Evidence behind certificate TS-CERT-2026-001. All results are from
the tree this record ships in (the manifest in this directory binds
the exact bytes).

## Automated gates

- **Full test suite (fresh CI-faithful venv, `pip install -e ".[dev]"`,
  proxy env stripped):** 191 passed, 0 failed — 178 at v0.2.0 plus 13
  calibration tests (factor math, the 20-sample application
  threshold, clamping, the 10% warning rule, persistence round-trip,
  corrupt-file recovery, 200-sample window eviction, and one
  end-to-end API test proving a learned factor changes planning and
  is recorded).
- **Coverage:** 84.79% total against the ≥80% CI gate;
  `spine/calibration.py` at 95%.
- **Lint/format/types:** `ruff check` clean, `ruff format --check`
  clean, `mypy` strict clean over `src`.
- **GitHub CI:** `verify (3.11)` and `verify (3.12)` green on the
  calibration PR (#21) and on this release PR — see the repository's
  Actions history for the runs bound to these commits.

## Behavior verification (live instance)

The public demo (spine.aimlds.org) runs this release on the local
profile against a local model, verified 2026-10-10 before release:

- `GET /api/v1/status` → ok; providers, tools, connectors listed.
- `GET /.well-known/agent-card.json` → the spine's A2A card.
- `GET /ui` → 200 (browser UI).
- `POST /api/v1/transform` with a plain-language intent → verdict
  **commit**, all gates passed (transport, output present, clean
  finish), answer recorded in the CTST ledger.
- `GET /api/v1/ledger/verify` → `valid: true` over the recorded
  entries (hash chain intact, including the earlier rejected cycle —
  attempts are recorded, not just successes).
- `POST /mcp` `tools/list` → the spine's tool surface.

## Prior record

v0.2.0 was released 2026-10-09 after an independent audit, a full
remediation program, and a solved report per finding; the ASFQC
gate record lives in `ASFQC/GATES.md`. This release changes no
v0.2.0 behavior except the additions and the one configuration fix
listed in `CHANGELOG.md`.
