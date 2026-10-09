"""Connector plugin auto-discovery tests.

Discovery sources: built-ins, the ``spine.connectors`` entry-point
group, and plugin directories (SPINE_CONNECTOR_PATH / ./connectors).
A broken plugin must be reported and skipped, never fatal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from spine.discovery import ConnectorRegistry, discover_connectors

_PLUGIN = '''
from spine.connectors import ConnectorResult, MCPConnector, ToolDef


class EchoConnector(MCPConnector):
    name = "echo-test"
    service_url = "http://localhost"

    def declare_capabilities(self):
        return [ToolDef(name="ping", description="Ping.",
                        input_schema={"type": "object", "properties": {}},
                        output_schema={"type": "object"})]

    def execute(self, tool, params):
        return ConnectorResult(success=True, tool=tool,
                               output={"pong": params}, connector=self.name)

    def health_check(self):
        return True
'''

_BROKEN = "raise RuntimeError('plugin exploded on import')\n"


def test_builtin_discovery() -> None:
    result = discover_connectors(include_entry_points=False)
    assert set(result.connectors) == {
        "github",
        "azure-devops",
        "jira",
        "servicenow",
        "databricks",
        "confluence",
    }
    assert result.sources["github"] == "builtin"


def test_directory_plugin_discovered_and_executed(tmp_path: Path) -> None:
    (tmp_path / "echo_conn.py").write_text(_PLUGIN)
    result = discover_connectors(
        search_paths=[tmp_path], include_entry_points=False
    )
    assert "echo-test" in result.connectors
    registry = ConnectorRegistry(result)
    conn = registry.get("echo-test")
    assert conn is not None
    out = conn.execute("ping", {"x": 1})
    assert out.success is True
    assert out.output == {"pong": {"x": 1}}
    described = {d["name"]: d for d in registry.describe()}
    assert described["echo-test"]["capabilities"] == ["ping"]
    assert described["echo-test"]["source"].startswith("path:")


def test_broken_plugin_reported_not_fatal(tmp_path: Path) -> None:
    (tmp_path / "bad_conn.py").write_text(_BROKEN)
    (tmp_path / "echo_conn.py").write_text(_PLUGIN)
    result = discover_connectors(
        search_paths=[tmp_path], include_entry_points=False
    )
    assert "echo-test" in result.connectors
    assert any("plugin exploded" in e for e in result.errors)


def test_env_var_path_and_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "echo_conn.py").write_text(_PLUGIN)
    monkeypatch.setenv("SPINE_CONNECTOR_PATH", str(tmp_path))
    monkeypatch.setenv("SPINE_CONNECTOR_GITHUB_TOKEN", "env-token-123")
    registry = ConnectorRegistry.discover(include_entry_points=False)
    assert "echo-test" in registry.names()
    gh = registry.get("github")
    assert gh is not None
    assert gh.token == "env-token-123"


def test_duplicate_names_keep_first(tmp_path: Path) -> None:
    (tmp_path / "dupe.py").write_text(
        _PLUGIN.replace('name = "echo-test"', 'name = "github"')
        .replace("EchoConnector", "DupeConnector")
    )
    result = discover_connectors(
        search_paths=[tmp_path], include_entry_points=False
    )
    assert result.connectors["github"].__name__ == "GitHubConnector"
    assert any("already registered" in s for s in result.skipped)


def test_missing_directory_reported(tmp_path: Path) -> None:
    result = discover_connectors(
        search_paths=[tmp_path / "nope"], include_entry_points=False
    )
    assert any("not a directory" in e for e in result.errors)


def test_api_connectors_endpoints(tmp_path: Path, monkeypatch: Any) -> None:
    from fastapi.testclient import TestClient

    import spine.api as api_module

    monkeypatch.setenv("SPINE_CTST_ROOT", str(tmp_path))
    monkeypatch.setenv("SPINE_CONTEXT_PATH", str(tmp_path / "ctx.json"))
    with TestClient(api_module.app) as client:
        resp = client.get("/api/v1/connectors")
        assert resp.status_code == 200
        names = {c["name"] for c in resp.json()["connectors"]}
        assert "github" in names and "servicenow" in names

        bad = client.post(
            "/api/v1/connectors/nope/execute",
            json={"tool": "x", "params": {}},
        )
        assert bad.status_code == 404

        status = client.get("/api/v1/status")
        assert "github" in status.json()["connectors"]
