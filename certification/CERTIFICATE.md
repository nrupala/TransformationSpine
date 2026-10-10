# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later

# Certificate of Verification — TransformationSpine

- **Certificate serial:** TS-CERT-2026-002
- **Product:** TransformationSpine v0.3.1
- **Issuer:** the TransformationSpine repository (self-issued,
  repo-native certification; verification is reproducible by anyone
  from the public tree — no trust in the issuer required)
- **Issued:** 2026-10-10
- **Valid until:** 2027-01-08 (90 days)
- **Supersedes:** TS-CERT-2026-001 (which remains valid for the
  v0.3.0 tree it certifies)

## What this certificate attests

The repository tree at the `v0.3.1` tag:

1. **Matches its manifest.** `certification/MANIFEST.sha256` lists a
   SHA-256 for every file in the tree (97 files; the manifest and
   this certificate are the only exclusions, so they cannot certify
   themselves). Verify with:

   ```sh
   python3 scripts/certify.py --check
   ```

   Manifest SHA-256:
   `25969274d1f5de698a6bcef4efa1e5dfcad9df6fb7c4336bdfa9870f9dfa6f40`

2. **Passed its own gates at issue time** — see
   `certification/TEST-RECORD.md` for the evidence: the full test
   suite, the ≥ 80% coverage gate, lint, formatting, and strict
   type checking, plus live behavior verification of the public demo
   redeployed from the certified tree.

## What this certificate does NOT attest

- Behavior of live cloud or hybrid providers against real accounts
  (certified paths use local and mocked provider tests).
- Enterprise connectors against real customer tenants.
- Availability or uptime of the public demo
  (https://spine.aimlds.org).
- Anything outside this repository tree, including composed stacks
  that embed the spine.

## Revocation

If a defect is found that invalidates an attestation above, this
certificate is revoked by a notice appended here in a new commit,
and the release it names is yanked with a pointer to the notice.
Re-issue after repair takes the next serial.
