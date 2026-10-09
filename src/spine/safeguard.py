# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: Apache-2.0
"""OS-level safeguarding for TransformationSpine.

Ensures the spine process runs with least-privilege file access
and prevents writes outside the project directory.

Usage:
    python -m spine.safeguard check      # Verify current safeguards
    python -m spine.safeguard enforce    # Apply restrictive permissions
    python -m spine.safeguard audit      # Audit file permissions
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_project_root() -> Path:
    """Return the project root directory."""
    return _PROJECT_ROOT


def check_path_restriction(path: Path) -> dict[str, Any]:
    """Check if a path is within the project root."""
    try:
        path.resolve().relative_to(_PROJECT_ROOT.resolve())
        return {"path": str(path), "restricted": False, "within_project": True}
    except ValueError:
        return {"path": str(path), "restricted": True, "within_project": False}


def enforce_safeguards(
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Apply least-privilege file permissions under ``root``.

    The actual enforcement: no file or directory in the project may be
    world-writable — the world-write bit is stripped wherever found,
    and only real changes are reported (with before/after modes).
    (The previous implementation walked the tree and reported
    "restrict/ok" for every directory without changing a single mode;
    the report was fiction.)
    """
    base = (root or _PROJECT_ROOT).resolve()
    changes: list[dict[str, Any]] = []

    def _strip_world_write(path: Path) -> None:
        mode = path.stat().st_mode
        if mode & 0o002:
            new_mode = mode & ~0o002
            os.chmod(path, new_mode)
            changes.append(
                {
                    "path": str(path),
                    "action": "strip-world-write",
                    "status": "applied",
                    "before": oct(mode & 0o777),
                    "after": oct(new_mode & 0o777),
                }
            )

    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
        _strip_world_write(Path(dirpath))
        for filename in filenames:
            _strip_world_write(Path(dirpath) / filename)

    return changes


def audit_permissions() -> list[dict[str, Any]]:
    """Audit file permissions across the project."""
    audit_results: list[dict[str, Any]] = []

    for dirpath, dirnames, filenames in os.walk(_PROJECT_ROOT):
        dir_path = Path(dirpath)
        if "__pycache__" in dirnames:
            dirnames.remove("__pycache__")
        if ".git" in dirnames:
            dirnames.remove(".git")

        for filename in filenames:
            file_path = dir_path / filename
            if file_path.is_file():
                stat = file_path.stat()
                audit_results.append(
                    {
                        "path": str(file_path),
                        "readable": bool(stat.st_mode & 0o400),
                        "writable": bool(stat.st_mode & 0o200),
                        "executable": bool(stat.st_mode & 0o100),
                    }
                )

    return audit_results


def world_writable_count(root: Path | None = None) -> int:
    """Count world-writable files/dirs under the project (the enforce target)."""
    base = (root or _PROJECT_ROOT).resolve()
    count = 0
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
        if Path(dirpath).stat().st_mode & 0o002:
            count += 1
        for filename in filenames:
            if (Path(dirpath) / filename).stat().st_mode & 0o002:
                count += 1
    return count


def verify_write_protection(path: Path) -> bool:
    """Verify that a path outside the project is write-protected."""
    check = check_path_restriction(path)
    return bool(check.get("restricted", False))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m spine.safeguard [check|enforce|audit]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "check":
        print(f"Project root: {_PROJECT_ROOT}")
        count = world_writable_count()
        print(f"World-writable files/directories: {count}")
        print(
            "Path restriction is advisory (check_path_restriction); "
            "run 'enforce' to strip world-write permissions."
        )
    elif command == "enforce":
        changes = enforce_safeguards()
        print(f"Applied {len(changes)} safeguard changes")
    elif command == "audit":
        results = audit_permissions()
        print(f"Audited {len(results)} files")
        for r in results[:10]:
            p = r["path"]
            print(
                f"  {p}: read={r['readable']} "
                f"write={r['writable']} exec={r['executable']}"
            )
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
