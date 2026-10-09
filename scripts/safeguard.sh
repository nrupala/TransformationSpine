#!/usr/bin/env bash
# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
# TransformationSpine safeguard check (BUILD_PLAN Phase 3 deliverable).
# Verifies the spine's OS-level safeguards from the repo root:
#   scripts/safeguard.sh [check|enforce|audit]
# Defaults to check. enforce strips world-writable permissions across
# the project tree and reports only the changes it actually applied.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 -m spine.safeguard "${1:-check}"
