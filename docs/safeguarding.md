<!-- Copyright 2026 Nrupal Akolkar -->
<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# OS-Level Safeguarding

This document describes how TransformationSpine implements OS-level file access controls to ensure the spine process operates with least-privilege security.

## Principle

Spine runs with minimal file access permissions:

- **Read access**: Full read access to the project directory
- **Write access**: Only to files within the project directory
- **Outside writes**: Rejected with appropriate error

This is achieved without Docker, using native OS mechanisms:
- Windows: Process-level ACLs and directory restrictions
- Linux/macOS: File permissions, `.gitignore` conventions, Python path enforcement

## Usage

### Check Safeguards
```bash
python -m spine.safeguard check
```

### Enforce Permissions
```bash
python -m spine.safeguard enforce
```

### Audit File Permissions
```bash
python -m spine.safeguard audit
```

## Python Integration

The safeguard module integrates with the spine runtime:

```python
from spine.safeguard import check_path_restriction, _PROJECT_ROOT


def safe_write(path: Path, content: str) -> None:
    if check_path_restriction(path)["restricted"]:
        raise PermissionError(f"Write to {path} rejected: outside project directory")
    path.write_text(content)
```

## Implementation Details

### Path Restriction Check
All file operations are validated against the project root:

```python
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # .../TransformationSpine


def verify_path(path: Path) -> Path:
    resolved = path.resolve()
    resolved.relative_to(PROJECT_ROOT)  # Raises ValueError if outside
    return resolved
```

### Git Ignore Integration
The safeguard respects `.gitignore` patterns:

- Generated files go into `.gitignore`
- Coverage reports excluded
- `__pycache__` ignored automatically
- Backup files (`.bak-*`) ignored

### Audit Trail
All file operations are logged to the CTST ledger when writing outside allowed paths:

```python
if not within_project:
    ctst_ledger.append(
        CTSTRecord(
            intent={"summary": "illegal_write_attempt", "path": str(path)},
            mechanism="safeguard",
            error_signal=1.0,
            committed=False,
        )
    )
```

## Rollback Strategy

If safeguards cause issues:

1. Disable runtime checks: `SPINE_SAFEGUARDS=0`
2. Revert specific permission changes: `git checkout .`
3. Remove safeguard module: `rm scripts/safeguard.py`

## Integration Points

### CLI Integration
The `spine_cli.py` validates paths before any file operation:

```python
from spine.safeguard import check_path_restriction


def safe_read(path_str: str) -> str:
    result = check_path_restriction(Path(path_str))
    if result["restricted"]:
        raise PermissionError(f"Access denied: {path_str}")
    return Path(path_str).read_text()
```

### Provider Adapters
File-based providers (e.g., local file storages) integrate safeguards:

```python
class FileProvider:
    def read(self, path: str) -> str:
        safe_path = verify_path(Path(path))
        return safe_path.read_text()
```

## Testing

Run safeguard tests:
```bash
python -m pytest tests/test_safeguard.py -v
```