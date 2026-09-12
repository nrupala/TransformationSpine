"""Tool-call abstraction tests for TransformationSpine.

Tests that ProviderResult supports tool_calls and that adapters
can parse tool-use responses from providers.
"""

from __future__ import annotations

from spine.result import ProviderResult


def test_provider_result_default_tool_calls_empty() -> None:
    """Default tool_calls is empty list."""
    result = ProviderResult(
        success=True,
        output="hello",
        provider="test",
        model="test-model",
    )
    assert result.tool_calls == []


def test_provider_result_with_tool_calls() -> None:
    """ProviderResult accepts tool_calls field."""
    tool_calls = [
        {
            "name": "search",
            "arguments": {"query": "test"},
            "id": "call_123",
        }
    ]
    result = ProviderResult(
        success=True,
        output="",
        provider="test",
        model="test-model",
        tool_calls=tool_calls,
    )
    assert result.tool_calls == tool_calls
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "search"


def test_provider_result_tool_calls_preserves_arguments() -> None:
    """Tool calls preserve the full argument dict."""
    tool_calls = [
        {
            "name": "compute",
            "arguments": {"x": 1, "y": 2},
            "id": "call_456",
        }
    ]
    result = ProviderResult(
        success=True,
        output="computed",
        provider="test",
        model="test-model",
        tool_calls=tool_calls,
    )
    assert result.tool_calls[0]["arguments"] == {"x": 1, "y": 2}


def test_provider_result_backward_compatibility() -> None:
    """Creating ProviderResult without tool_calls still works."""
    result = ProviderResult(
        success=True,
        output="test output",
        provider="llama.cpp",
        model="Qwen3.5-9B-Q8_0",
        error_signal=0.0,
    )
    assert result.tool_calls == []
    assert result.is_converged is True
