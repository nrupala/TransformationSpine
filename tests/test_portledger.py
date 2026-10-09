# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Vendored PortLedger (spine.portledger) — smoke + behavior tests."""

import json

from spine.portledger import PortLedger, __version__


def test_version_present():
    assert __version__ == "0.1.0"


def test_allocate_prefers_free(tmp_path):
    pl = PortLedger(tmp_path / "l.jsonl", tmp_path / "s.json")
    a = pl.allocate("spine-api", 22880)
    assert a.actual == 22880
    assert a.via == "preferred"
    assert pl.resolve("spine-api") == 22880


def test_conflict_scan(tmp_path, monkeypatch):
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 22890))
    s.listen(1)
    try:
        pl = PortLedger(tmp_path / "l.jsonl", tmp_path / "s.json")
        a = pl.allocate("x", 22890, 22890, 22899)
        assert a.actual == 22891
        assert a.via == "scan"
    finally:
        s.close()


def test_advertised_snapshot(tmp_path):
    pl = PortLedger(tmp_path / "l.jsonl", tmp_path / "s.json")
    pl.allocate("aioa", 22901)
    data = json.loads((tmp_path / "s.json").read_text())
    assert data["aioa"]["port"] == 22901
