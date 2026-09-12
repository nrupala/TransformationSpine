"""OS-level safeguarding tests for TransformationSpine."""

from __future__ import annotations

from pathlib import Path

from spine.safeguard import (
    check_path_restriction,
    enforce_safeguards,
    get_project_root,
    verify_write_protection,
)


def test_get_project_root_is_project_directory() -> None:
    """Project root is the spine repository directory."""
    root = get_project_root()
    assert root.name == "TransformationSpine"
    assert root.exists()


def test_check_path_restriction_accepts_project_path() -> None:
    """Paths inside the project are allowed."""
    root = get_project_root()
    result = check_path_restriction(root / "src")
    assert result["restricted"] is False
    assert result["within_project"] is True


def test_check_path_restriction_rejects_outside_path() -> None:
    """Paths outside the project are restricted."""
    outside = Path("/tmp/outside-test")
    result = check_path_restriction(outside)
    assert result["restricted"] is True
    assert result["within_project"] is False


def test_verify_write_protection_rejects_outside_path() -> None:
    """Write protection rejects paths outside the project."""
    outside = Path("/tmp/outside-test")
    assert verify_write_protection(outside) is True


def test_enforce_safeguards_is_idempotent() -> None:
    """Safeguard enforcement is idempotent."""
    first = enforce_safeguards()
    second = enforce_safeguards()
    assert first == second
    assert isinstance(first, list)
