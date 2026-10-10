# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later

# Certificate TS-CERT-2026-001

**Product:** TransformationSpine v0.3.0 (this repository, at the
v0.3.0 release tag)

**Issuer:** Wright (Muse by Meta), for Nrupal Akolkar

**Issued:** 2026-10-10 · **Valid until:** 2027-01-08 (90 days)

**Manifest:** `certification/MANIFEST.sha256` — 96 files
**Manifest SHA-256:**
`2f2fe4899d8e22a4096491d14b9cc5707e9dba990c5a1d5164429010ccbb80af`

**Verify it yourself** (no trust in the issuer required):

```
python3 scripts/certify.py --check
```

## What this certificate attests

- The tree at the v0.3.0 tag is byte-for-byte the tree described by
  the manifest above.
- That tree passes the gates recorded in
  `certification/TEST-RECORD.md`: the full test suite (191 tests,
  coverage 84.79% against a ≥80% gate), ruff and mypy clean, CI
  green on Python 3.11 and 3.12, and a live behavior pass on the
  public demo instance (gated transform committed; CTST ledger
  verifies).
- v0.3.0 closes the development plan recorded in `ROADMAP.md` and
  `BUILD_PLAN.md`, including the final open item, estimator
  calibration.

## What it does NOT certify

- Live behavior of the cloud and hybrid profiles against real
  provider accounts (no credentials in the test environment; the
  adapters are covered by tests, not by live calls).
- Live behavior of the enterprise connectors against real tenants
  (covered by test doubles and recorded fixtures).
- Uptime or availability of the public demo — an operational
  property, not a property of this tree.
- Anything outside this repository's tree, including composed
  stacks that embed the spine.

## Revocation

If a defect is found that invalidates an attestation above, the
issuer will publish a revocation notice in this directory naming
this serial, and the certificate is void from that notice onward.
Expiry at the validity date ends the attestation until a
re-verification issues a successor certificate.
