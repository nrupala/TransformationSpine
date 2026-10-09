# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
"""CTST hash-chain integrity tests (audit F-01 regression suite).

These tests fail against the pre-fix implementation, where append()
computed a hash but never persisted it and verify_chain() could not
detect edits. They are the behavioral proof for the tamper-evidence
claim: write records, edit the stored bytes, verification must fail.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from spine.ctst import CTSTLedger, CTSTRecord


def _record(result: str) -> CTSTRecord:
    return CTSTRecord(
        mechanism="test",
        outcome={"result": result},
        committed=True,
    )


def _ledger_file(root: Path) -> Path:
    return next(root.glob("ctst_*.jsonl"))


def test_append_persists_hash_fields(tmp_path: Path) -> None:
    led = CTSTLedger(root=tmp_path)
    h1 = led.append(_record("one"))
    line = json.loads(_ledger_file(tmp_path).read_text().splitlines()[0])
    assert line["record_hash"] == h1
    assert line["prev_hash"] == ""


def test_chain_links_and_verifies(tmp_path: Path) -> None:
    led = CTSTLedger(root=tmp_path)
    led.append(_record("one"))
    led.append(_record("two"))
    lines = [json.loads(x) for x in _ledger_file(tmp_path).read_text().splitlines()]
    assert lines[1]["prev_hash"] == lines[0]["record_hash"]
    assert led.verify_chain() is True
    assert led.head_hash == lines[1]["record_hash"]


def test_chain_survives_restart_and_continues(tmp_path: Path) -> None:
    led = CTSTLedger(root=tmp_path)
    led.append(_record("one"))
    led.append(_record("two"))

    led2 = CTSTLedger(root=tmp_path)  # fresh process view of same files
    assert led2.verify_chain() is True
    led2.append(_record("three"))
    lines = [json.loads(x) for x in _ledger_file(tmp_path).read_text().splitlines()]
    assert lines[2]["prev_hash"] == lines[1]["record_hash"]
    assert led2.verify_chain() is True


def test_tampered_content_fails_verification(tmp_path: Path) -> None:
    led = CTSTLedger(root=tmp_path)
    led.append(_record("original"))
    led.append(_record("second"))
    assert led.verify_chain() is True

    f = _ledger_file(tmp_path)
    f.write_text(f.read_text().replace("original", "TAMPERED"))

    assert led.verify_chain() is False
    assert CTSTLedger(root=tmp_path).verify_chain() is False


def test_tampered_hash_field_fails_verification(tmp_path: Path) -> None:
    led = CTSTLedger(root=tmp_path)
    led.append(_record("one"))
    led.append(_record("two"))
    f = _ledger_file(tmp_path)
    lines = f.read_text().splitlines()
    data = json.loads(lines[0])
    data["record_hash"] = "0" * 64
    lines[0] = json.dumps(data)
    f.write_text("\n".join(lines) + "\n")
    assert CTSTLedger(root=tmp_path).verify_chain() is False


def test_deleted_middle_record_fails_verification(tmp_path: Path) -> None:
    led = CTSTLedger(root=tmp_path)
    for i in range(3):
        led.append(_record(f"r{i}"))
    f = _ledger_file(tmp_path)
    lines = f.read_text().splitlines()
    del lines[1]
    f.write_text("\n".join(lines) + "\n")
    assert CTSTLedger(root=tmp_path).verify_chain() is False


def test_legacy_lines_without_hashes_do_not_break_chain(tmp_path: Path) -> None:
    """Ledgers written before hashes were persisted must still verify
    (transitively) and accept new chained appends."""
    legacy = _record("legacy")
    f = tmp_path / "ctst_2026-01-01.jsonl"
    legacy_dict = legacy.to_dict()
    legacy_dict.pop("prev_hash")
    legacy_dict.pop("record_hash")
    f.write_text(json.dumps(legacy_dict, default=str) + "\n")

    led = CTSTLedger(root=tmp_path)
    led.append(_record("new"))
    assert led.verify_chain() is True


def test_ledger_verify_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from spine.api import create_app

    # The API builds its own ledger at lifespan from the env root.
    monkeypatch.setenv("SPINE_CTST_ROOT", str(tmp_path))
    led = CTSTLedger(root=tmp_path)
    led.append(_record("one"))
    with TestClient(create_app()) as client:
        resp = client.get("/api/v1/ledger/verify")
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["records"] >= 1
