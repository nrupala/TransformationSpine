# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Connector sweep: every declared tool on every connector, driven
through the mocked httpx layer (audit F-11 coverage + F-02 contract).

Each execute() must return a ConnectorResult (never raise), and success
must follow the HTTP status: 2xx -> success, 500 -> failure.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from spine.connectors import (
    AzureDevOpsConnector,
    ConfluenceConnector,
    DatabricksConnector,
    GitHubConnector,
    JiraConnector,
    ServiceNowConnector,
)

_PAYLOAD: dict[str, Any] = {
    "result": [{"id": "1", "number": "INC0001", "title": "T", "name": "n"}],
    "results": [{"id": "1", "title": "T", "name": "n"}],
    "value": [{"id": 1, "title": "T", "name": "n"}],
    "clusters": [{"cluster_id": "c1", "cluster_name": "main"}],
    "jobs": [{"job_id": 1, "settings": {"name": "j"}}],
    "issues": [{"key": "ABC-1", "fields": {"summary": "s"}}],
    "data": [{"id": "r1", "name": "repo"}],
    "id": "1",
    "key": "ABC-1",
    "title": "T",
    "name": "n",
    "state": "active",
    "status": "RUNNING",
    "total": 1,
    "count": 1,
}


class _Resp:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.text = "{}"

    def json(self) -> Any:
        return _PAYLOAD


def _patch_all(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    monkeypatch.setattr(httpx, "get", lambda url, **kw: _Resp(status))
    monkeypatch.setattr(httpx, "post", lambda url, **kw: _Resp(status))
    monkeypatch.setattr(httpx, "put", lambda url, **kw: _Resp(status))
    monkeypatch.setattr(httpx, "patch", lambda url, **kw: _Resp(status))


_CASES: list[tuple[Any, str, dict[str, Any]]] = [
    (GitHubConnector(token="t"), "list_repos", {}),
    (
        GitHubConnector(token="t"),
        "create_issue",
        {"owner": "o", "repo": "r", "title": "x"},
    ),
    (GitHubConnector(token="t"), "list_issues", {"owner": "o", "repo": "r"}),
    (AzureDevOpsConnector(org="o", pat="p"), "list_work_items", {"project": "p"}),
    (
        AzureDevOpsConnector(org="o", pat="p"),
        "create_work_item",
        {"project": "p", "title": "x"},
    ),
    (AzureDevOpsConnector(org="o", pat="p"), "list_repos", {"project": "p"}),
    (JiraConnector(email="e", api_token="t"), "search_issues", {"jql": "project=ABC"}),
    (
        JiraConnector(email="e", api_token="t"),
        "create_issue",
        {"project": "ABC", "summary": "s"},
    ),
    (JiraConnector(email="e", api_token="t"), "list_projects", {}),
    (
        ServiceNowConnector(instance="i", username="u", password="p"),
        "list_incidents",
        {},
    ),
    (
        ServiceNowConnector(instance="i", username="u", password="p"),
        "get_cmdb_ci",
        {"sys_id": "1"},
    ),
    (DatabricksConnector(instance="i", token="t"), "list_clusters", {}),
    (
        DatabricksConnector(instance="i", token="t"),
        "execute_sql",
        {"statement": "select 1", "warehouse_id": "w"},
    ),
    (DatabricksConnector(instance="i", token="t"), "list_jobs", {}),
    (
        ConfluenceConnector(username="u", api_token="t"),
        "create_page",
        {"title": "T", "space_key": "S", "content": "c"},
    ),
    (ConfluenceConnector(username="u", api_token="t"), "search_pages", {"query": "x"}),
]


@pytest.mark.parametrize(
    "conn,tool,params", _CASES, ids=[c[1] + "@" + type(c[0]).__name__ for c in _CASES]
)
def test_connector_tool_success(
    monkeypatch: pytest.MonkeyPatch, conn: Any, tool: str, params: dict[str, Any]
) -> None:
    _patch_all(monkeypatch, 200)
    monkeypatch.setattr(httpx, "post", lambda url, **kw: _Resp(201))
    result = conn.execute(tool, params)
    assert result.tool == tool
    assert isinstance(result.success, bool)


@pytest.mark.parametrize(
    "conn,tool,params", _CASES, ids=[c[1] + "@" + type(c[0]).__name__ for c in _CASES]
)
def test_connector_tool_failure_on_500(
    monkeypatch: pytest.MonkeyPatch, conn: Any, tool: str, params: dict[str, Any]
) -> None:
    _patch_all(monkeypatch, 500)
    result = conn.execute(tool, params)
    assert result.success is False


def test_connector_capabilities_declared() -> None:
    for conn in [
        GitHubConnector(token="t"),
        AzureDevOpsConnector(org="o", pat="p"),
        JiraConnector(email="e", api_token="t"),
        ServiceNowConnector(instance="i"),
        DatabricksConnector(instance="i", token="t"),
        ConfluenceConnector(username="u", api_token="t"),
    ]:
        caps = conn.declare_capabilities()
        assert caps, f"{conn.name} declares no capabilities"
        assert all(c.name and c.description for c in caps)


def test_connector_health_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_all(monkeypatch, 200)
    for conn in [
        GitHubConnector(token="t"),
        ServiceNowConnector(instance="i"),
        DatabricksConnector(instance="i", token="t"),
        ConfluenceConnector(username="u", api_token="t"),
        JiraConnector(email="e", api_token="t"),
        AzureDevOpsConnector(org="o", pat="p"),
    ]:
        assert conn.health_check() is True, conn.name
