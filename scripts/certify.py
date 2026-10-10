# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Generate or verify the certification manifest for this tree.

The manifest (certification/MANIFEST.sha256) binds the release: every
file in the tree, hashed with SHA-256, sorted by path. Anyone can
re-check the tree against the certificate without trusting the
issuer:

    python3 scripts/certify.py --check

Excluded by design: .git and build/cache artifacts; the manifest
itself; and CERTIFICATE.md — the certificate is the binder, not one
of the bound files (it quotes the manifest's own hash instead).
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "certification" / "MANIFEST.sha256"

EXCLUDED_DIRS = {".git", "__pycache__", ".venv", "node_modules", "htmlcov"}
EXCLUDED_FILES = {"certification/MANIFEST.sha256", "certification/CERTIFICATE.md"}
EXCLUDED_SUFFIXES = (".egg-info",)


def tree_files() -> list[Path]:
    out: list[Path] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        if any(part.endswith(EXCLUDED_SUFFIXES) for part in rel.parts):
            continue
        if rel.as_posix() in EXCLUDED_FILES or rel.name == ".coverage":
            continue
        out.append(path)
    return out


def manifest_lines() -> list[str]:
    lines = []
    for path in tree_files():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(ROOT).as_posix()}")
    return lines


def main() -> int:
    if "--check" in sys.argv:
        expected = MANIFEST.read_text(encoding="utf-8").splitlines()
        actual = manifest_lines()
        if expected == actual:
            print(f"OK: manifest matches tree ({len(actual)} files)")
            return 0
        exp, act = set(expected), set(actual)
        for line in sorted(act - exp):
            print(f"CHANGED/NEW: {line.split('  ', 1)[1]}")
        for line in sorted(exp - act):
            print(f"MISSING/STALE: {line.split('  ', 1)[1]}")
        print(f"FAIL: manifest covers {len(expected)}, tree has {len(actual)}")
        return 1
    lines = manifest_lines()
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8")
    digest = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    print(f"wrote {MANIFEST.relative_to(ROOT)}: {len(lines)} files")
    print(f"manifest sha256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
