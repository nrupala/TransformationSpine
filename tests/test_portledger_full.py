"""portledger to full coverage (owner directive: 100%).

The pre-existing test_portledger.py covered the happy paths (~61%).
This file pins every remaining branch: who_listens parsing and
failure, random fallback, scan exhaustion, corrupt state files,
prior-owner recording, resolve type guards, status log parsing, and
the whole CLI including the __main__ guard.
"""

from __future__ import annotations

import json
import runpy
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from spine import portledger
from spine.portledger import PortLedger


def _ledger(tmp_path: Path) -> PortLedger:
    return PortLedger(tmp_path / "ledger.jsonl", tmp_path / "state.json")


# -- port_free ---------------------------------------------------------


def test_port_free_false_when_bound() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    try:
        assert portledger.port_free(port) is False
    finally:
        sock.close()
    assert portledger.port_free(port) is True


# -- who_listens ---------------------------------------------------------


class _FakeRun:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout


def test_who_listens_parses_listening_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = (
        "  TCP    127.0.0.1:9001   0.0.0.0:0   LISTENING   4242\n"
        "  TCP    127.0.0.1:9002   0.0.0.0:0   TIME_WAIT   99\n"
    )
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: _FakeRun(out)
    )
    lines = portledger.who_listens(9001)
    assert lines is not None and "4242" in lines[0]
    assert portledger.who_listens(7777) is None  # no match -> None


def test_who_listens_failure_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*a: Any, **k: Any) -> Any:
        raise OSError("netstat missing")

    monkeypatch.setattr(subprocess, "run", boom)
    assert portledger.who_listens(9001) is None


# -- _rand_free / scan_free ----------------------------------------------


def test_rand_free_skips_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    picks = iter([41001, 41002])
    monkeypatch.setattr(
        portledger.random, "randint", lambda a, b: next(picks)
    )
    monkeypatch.setattr(
        portledger, "port_free", lambda p: p == 41002
    )
    assert portledger._rand_free() == 41002


def test_scan_free_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(portledger, "port_free", lambda p: p == 5003)
    assert portledger.scan_free(5000, 5000, 5005) == 5003
    # default range is just the preferred port, which is skipped
    assert portledger.scan_free(5000, None, None) is None
    monkeypatch.setattr(portledger, "port_free", lambda p: False)
    assert portledger.scan_free(5000, 5000, 5002) is None


# -- PortLedger state handling --------------------------------------------


def test_current_corrupt_state_returns_empty(tmp_path: Path) -> None:
    led = _ledger(tmp_path)
    (tmp_path / "state.json").write_text("{not json", encoding="utf-8")
    assert led.current() == {}


def test_allocate_records_prior_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    led = _ledger(tmp_path)
    monkeypatch.setattr(
        portledger, "who_listens", lambda p: ["  TCP ... LISTENING  7"]
    )
    alloc = led.allocate("svc", 0)  # port 0 binds free -> preferred path
    rows = led.status()
    assert rows and rows[0]["prior_owner"] == ["  TCP ... LISTENING  7"]
    assert alloc.service == "svc"


def test_allocate_scan_and_random_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    led = _ledger(tmp_path)
    # preferred busy -> scan finds one
    monkeypatch.setattr(portledger, "port_free", lambda p, h="127.0.0.1": False)
    monkeypatch.setattr(portledger, "scan_free", lambda *a: 31_001)
    alloc = led.allocate("svc", 30000, 30000, 30010)
    assert (alloc.actual, alloc.via) == (31_001, "scan")
    # scan exhausted -> random
    monkeypatch.setattr(portledger, "scan_free", lambda *a: None)
    monkeypatch.setattr(portledger, "_rand_free", lambda: 41_555)
    alloc = led.allocate("svc", 30000, 30000, 30010)
    assert (alloc.actual, alloc.via) == (41_555, "random")


def test_resolve_type_guards(tmp_path: Path) -> None:
    led = _ledger(tmp_path)
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "good": {"port": 8080},
                "strport": {"port": "8080"},
                "notdict": 42,
            }
        ),
        encoding="utf-8",
    )
    assert led.resolve("good") == 8080
    assert led.resolve("strport") is None
    assert led.resolve("notdict") is None
    assert led.resolve("absent") is None


def test_status_missing_and_messy_ledger(tmp_path: Path) -> None:
    led = _ledger(tmp_path)
    assert led.status() == []  # no ledger file yet
    (tmp_path / "ledger.jsonl").write_text(
        '\n{"a": 1}\nnot json\n{"b": 2}\n', encoding="utf-8"
    )
    assert led.status() == [{"a": 1}, {"b": 2}]


# -- CLI --------------------------------------------------------------------


def _run_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    tmp_path: Path,
) -> str:
    full = argv + [
        "--ledger",
        str(tmp_path / "ledger.jsonl"),
        "--state",
        str(tmp_path / "state.json"),
    ]
    monkeypatch.setattr(sys, "argv", ["portledger"] + full)
    portledger._cli()
    return capsys.readouterr().out


def test_cli_version(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["portledger", "--version"])
    portledger._cli()
    assert "portledger 0.1.0" in capsys.readouterr().out


def test_cli_status_current_who_allocate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = _run_cli(
        monkeypatch, capsys, ["--service", "svc", "--preferred", "0"], tmp_path
    )
    assert '"service": "svc"' in out

    out = _run_cli(monkeypatch, capsys, ["--status"], tmp_path)
    assert '"svc"' in out

    out = _run_cli(monkeypatch, capsys, ["--current"], tmp_path)
    assert '"svc"' in out

    out = _run_cli(monkeypatch, capsys, ["--who", "65000"], tmp_path)
    assert "65000" in out  # listener list or the no-listener message

    monkeypatch.setattr(portledger, "who_listens", lambda p: ["pid 1"])
    out = _run_cli(monkeypatch, capsys, ["--who", "65000"], tmp_path)
    assert "pid 1" in out


def test_cli_range_and_missing_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out = _run_cli(
        monkeypatch,
        capsys,
        ["--service", "svc2", "--preferred", "0", "--range", "31000-31002"],
        tmp_path,
    )
    assert '"service": "svc2"' in out

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "portledger",
            "--ledger",
            str(tmp_path / "l.jsonl"),
            "--state",
            str(tmp_path / "s.json"),
        ],
    )
    with pytest.raises(SystemExit):
        portledger._cli()


def test_main_guard_runs_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["portledger", "--version"])
    runpy.run_module("spine.portledger", run_name="__main__")
