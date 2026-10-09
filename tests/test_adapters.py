# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Adapter tests (BUILD_PLAN Phase 1 promised this file; audit F-05).

Drives the HuggingFace provider against an httpx MockTransport: the
adapter must send its auth header, parse the completion, and populate
usage/telemetry. Also pins the package exports for both HF adapters.
"""

from __future__ import annotations

import json

import httpx

import spine
from spine.adapters import HuggingFaceProvider


def _mock_client(payload: dict, status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") == "Bearer test-key"
        body = json.loads(request.content)
        assert body["model"] == "google/gemma-2b-it"
        return httpx.Response(status, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_hf_adapters_are_exported() -> None:
    assert hasattr(spine, "HuggingFaceProvider")
    assert hasattr(spine, "HuggingFaceLocalProvider")


def test_huggingface_complete_via_mock() -> None:
    provider = HuggingFaceProvider(api_key="test-key")
    provider.client = _mock_client(
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "hf says hi"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        }
    )
    result = provider.complete("hello")
    assert result.success is True
    assert result.output == "hf says hi"
    assert result.usage["total_tokens"] == 10
    assert result.telemetry["total_tokens"] == 10


def test_huggingface_error_status() -> None:
    provider = HuggingFaceProvider(api_key="test-key")
    provider.client = _mock_client({}, status=503)
    result = provider.complete("hello")
    assert result.success is False
    assert result.error_signal == 1.0
