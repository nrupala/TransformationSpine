# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later

# Test Record — TransformationSpine v0.3.1

Evidence behind certificate **TS-CERT-2026-002**, recorded
2026-10-10. Automated gates run in a fresh virtual environment
with `pip install -e ".[dev]"` and the proxy environment stripped
(the ambient sandbox proxy variables corrupt HTTP client tests and
do not exist in CI; CI on GitHub runs the same suite clean).

## Automated gates (local, CI-faithful)

| Gate | Result |
| --- | --- |
| Test suite | **193 passed** (191 at v0.3.0 + 2 UI regression tests) |
| Coverage | **85% total**, above the ≥ 80% floor |
| `ruff check` | clean |
| `ruff format --check` | clean |
| `mypy` (strict, src) | clean |
| Manifest self-check | `scripts/certify.py --check` — OK, 97 files |

GitHub CI for the release PR runs the same suite on Python 3.11
and 3.12; the release is tagged only on green.

## Behavior evidence

- `GET /` on the new build returns the browser UI (200, byte-equal
  to `GET /ui`) — the regression the release exists to fix.
- The public demo (https://spine.aimlds.org) is redeployed from
  the tagged v0.3.1 tree; its root URL serves the new UI, and a
  real transform through the public tunnel returns a committed
  verdict against the on-box model — recorded in the release notes.

## What was not re-verified for this patch

- The v0.3.0 behavior evidence stands for all unchanged surfaces;
  this patch changes only the browser UI, the root route, and
  version identifiers.
