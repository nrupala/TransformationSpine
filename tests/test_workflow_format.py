# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Workflow format tests: parse/serialize/Mermaid/validate round-trips
and the remaining API read endpoints (audit F-11 coverage)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spine.safeguard import audit_permissions, verify_write_protection
from spine.workflow import (
    generate_mermaid,
    load_workflow,
    parse_workflow,
    save_workflow,
    validate_workflow,
    workflow_from_template,
)


def test_parse_and_roundtrip(tmp_path: Path) -> None:
    wf = workflow_from_template("roundtrip", profile="cloud")
    path = tmp_path / "wf.json"
    save_workflow(wf, path)
    loaded = load_workflow(path)
    assert loaded.name == "roundtrip"
    assert loaded.profile == "cloud"
    assert len(loaded.nodes) == len(wf.nodes)
    assert validate_workflow(loaded) == []


def test_parse_rejects_dangling_edge() -> None:
    data = {
        "name": "bad",
        "nodes": [{"id": "a", "label": "A", "type": "input"}],
        "edges": [{"from": "a", "to": "ghost"}],
    }
    try:
        parse_workflow(data)
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "unknown node" in str(e)


def test_mermaid_rendering() -> None:
    wf = workflow_from_template("mmd")
    text = generate_mermaid(wf)
    assert text.startswith("```mermaid")
    assert "graph TD" in text
    assert "input --> context" in text
    assert "[action: provider.complete]" in text


def test_validate_reports_problems() -> None:
    wf = workflow_from_template("v")
    wf.nodes[1].action = ""
    errors = validate_workflow(wf)
    assert any("requires an action" in e for e in errors)


def test_safeguard_audit_shape() -> None:
    results = audit_permissions()
    assert results, "audit must see the project files"
    first = results[0]
    assert {"path", "readable", "writable", "executable"} <= set(first)
    assert verify_write_protection(Path("/tmp/definitely-outside")) is True


def test_api_read_endpoints(tmp_path: Path, monkeypatch: Any) -> None:
    from fastapi.testclient import TestClient

    import spine.api as api_module

    monkeypatch.setenv("SPINE_CTST_ROOT", str(tmp_path))
    monkeypatch.setenv("SPINE_CONTEXT_PATH", str(tmp_path / "ctx.json"))
    with TestClient(api_module.app) as client:
        status = client.get("/api/v1/status")
        assert status.status_code == 200
        body = status.json()
        assert body["status"] == "ok"
        assert "safeguards" in body
        assert "tools" in body
        assert "calculator" in body["tools"]

        ctx = client.get("/api/v1/context")
        assert ctx.status_code == 200

        ledger = client.get("/api/v1/ledger")
        assert ledger.status_code == 200
        assert "records" in ledger.json()

        bad = client.post(
            "/api/v1/transform",
            params={"intent": "x", "provider": "nope"},
        )
        assert bad.status_code == 400

        bad_scope = client.post(
            "/api/v1/transform",
            params={"intent": "x", "provider": "llama.cpp", "scope": "BOGUS"},
        )
        assert bad_scope.status_code in (400, 503)
        # The serialized app metadata must not drift from the package.
        spec = client.get("/openapi.json").json()
        import spine

        assert spec["info"]["version"] == spine.__version__
        _ = json.dumps(spec)
