"""Connector tests for the Phase-2 connectors (audit F-02).

The connectors are real HTTP clients; these tests drive them with a
monkeypatched httpx layer and pin the contract: success follows the
HTTP status, health checks really probe, and Confluence get_page by ID
actually sends its request (a dead branch made it always fail).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

import spine
from spine.connectors import (
    ConfluenceConnector,
    DatabricksConnector,
    ServiceNowConnector,
)


class _Resp:
    def __init__(self, status_code: int, payload: Any = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self) -> Any:
        return self._payload


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    get: Any = None,
    post: Any = None,
) -> dict[str, Any]:
    calls: dict[str, Any] = {"get": [], "post": []}
    if get is not None:

        def _get(url: str, **kw: Any) -> Any:
            calls["get"].append((url, kw))
            return get(url, **kw)

        monkeypatch.setattr(httpx, "get", _get)
    if post is not None:

        def _post(url: str, **kw: Any) -> Any:
            calls["post"].append((url, kw))
            return post(url, **kw)

        monkeypatch.setattr(httpx, "post", _post)
    return calls


def test_new_connectors_are_exported() -> None:
    for name in ("ServiceNowConnector", "DatabricksConnector", "ConfluenceConnector"):
        assert hasattr(spine, name), f"{name} missing from package exports"


def test_servicenow_create_incident_success_on_201(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {"result": {"number": "INC1"}}
    _patch(monkeypatch, post=lambda url, **kw: _Resp(201, payload))
    conn = ServiceNowConnector(instance="dev", username="u", password="p")
    result = conn.execute("create_incident", {"short_description": "boom"})
    assert result.success is True
    assert result.output["result"]["number"] == "INC1"


def test_servicenow_create_incident_failure_on_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch(monkeypatch, post=lambda url, **kw: _Resp(500, {}))
    conn = ServiceNowConnector(instance="dev", username="u", password="p")
    result = conn.execute("create_incident", {"short_description": "boom"})
    assert result.success is False


def test_servicenow_health_check_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, get=lambda url, **kw: _Resp(200, {}))
    conn = ServiceNowConnector(instance="dev")
    assert conn.health_check() is True

    def _boom(url: str, **kw: Any) -> Any:
        raise httpx.ConnectError("down", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", _boom)
    assert conn.health_check() is False


def test_databricks_list_clusters(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(
        monkeypatch,
        get=lambda url, **kw: _Resp(200, {"clusters": [{"cluster_id": "c1"}]}),
    )
    conn = DatabricksConnector(instance="w", token="t")
    result = conn.execute("list_clusters", {})
    assert result.success is True
    assert result.output["clusters"][0]["cluster_id"] == "c1"


def test_confluence_get_page_by_id_sends_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: the page_id branch built the URL but never sent it."""
    calls = _patch(
        monkeypatch,
        get=lambda url, **kw: _Resp(200, {"id": "42", "title": "Spec"}),
    )
    conn = ConfluenceConnector(base_url="https://example.atlassian.net/wiki")
    result = conn.execute("get_page", {"page_id": "42"})
    assert calls["get"], "get_page by id must issue an HTTP GET"
    assert result.success is True
    assert result.output["title"] == "Spec"


def test_confluence_get_page_by_title(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(
        monkeypatch,
        get=lambda url, **kw: _Resp(200, {"results": [{"id": "7", "title": "T"}]}),
    )
    conn = ConfluenceConnector(base_url="https://example.atlassian.net/wiki")
    result = conn.execute("get_page", {"title": "T", "space_key": "ENG"})
    assert result.success is True
    assert result.output["id"] == "7"
