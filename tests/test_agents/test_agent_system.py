# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the agent skill system."""

from __future__ import annotations

import tempfile

from spine.agents import AgentResult, code_review, generate_tests


def test_agent_skill_loading() -> None:
    """Test that we can list and load agent skills."""
    # In a real scenario this would check the local skills directory
    # For now we test the functions exist
    assert callable(code_review)
    assert callable(generate_tests)


def test_agent_result_dataclass() -> None:
    """Test the AgentResult dataclass."""
    result = AgentResult(
        success=True,
        output="test output",
        errors=["error1", "error2"],
        metadata={"key": "value"},
    )
    assert result.success is True
    assert result.output == "test output"
    assert result.errors == ["error1", "error2"]
    assert result.metadata == {"key": "value"}


def test_code_review_integration() -> None:
    """Test code_review integration with a temporary file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("# Good code\nprint('hello')\n")
        fname = f.name
    try:
        result = code_review(fname)
        # Should succeed or at least run without crashing
        assert isinstance(result, AgentResult)
        assert hasattr(result, "success")
        assert hasattr(result, "output")
        assert hasattr(result, "errors")
    finally:
        import os

        os.unlink(fname)


def test_generate_tests_integration() -> None:
    """Test generate_tests integration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mod = f"{tmpdir}/testmod.py"
        out = f"{tmpdir}/test_testmod.py"
        # Create a simple module
        with open(mod, "w") as f:
            f.write("# Test module\nVALUE = 42\n")
        # Generate tests
        result = generate_tests(mod, out)
        assert isinstance(result, AgentResult)
        assert result.success is True
        assert "Generated tests at" in result.output
        # Check file was created
        import os

        assert os.path.exists(out)
        with open(out) as f:
            content = f.read()
            assert "test_module_exists" in content
