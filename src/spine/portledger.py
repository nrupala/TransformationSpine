# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: Apache-2.0
# Vendored from D:\research\port-ledger (PortLedger v0.1.0, tag v0.1.0).
# Source of record: D:\research\port-ledger\portledger.py — keep in sync there.
# License: Apache-2.0. Stdlib-only.
"""portledger — dynamic port allocation with conflict resolution and record keeping.

A small, dependency-free (stdlib only) library + CLI for services that must
COEXIST on one host and avoid port conflicts with other real-world software.

Core concepts
-------------
* ``request(service, preferred, range)`` selects a port:
  1. if ``preferred`` is free it is used,
  2. else the next free port inside an optional range is scanned,
  3. else a random free port in 1024..65535 is selected,
  4. the binding is *probed* (TCP connect) before being returned.
* Every selection is recorded in an append-only ``ledger.jsonl`` (one JSON
  object per line) for auditing and by connectors that need the final port.
* ``advertise`` writes a "current state" JSON snapshot (``ports.current.json``)
  so connectors (opencode, ai client configs, supervisors) can read
  ``service -> port`` without parsing the log.

CLI
---
    python -m portledger --service aioa  --preferred 11199 --range 11190-11210
    python -m portledger --status
    python -m portledger --resolve-used            # who occupies a port (netstat)
"""

from __future__ import annotations

import argparse
import contextlib
import json
import random
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_LEDGER = Path.home() / ".portledger" / "ledger.jsonl"
DEFAULT_STATE = Path.home() / ".portledger" / "ports.current.json"
MIN_RANDOM = 1024
MAX_RANDOM = 65535

# Single source of truth for the package version (semver, see CHANGELOG.md).
# pyproject.toml `version` MUST match this value.
__version__ = "0.1.0"


def port_free(port: int, host: str = "127.0.0.1", timeout: float = 0.25) -> bool:
    """Return True when we can bind (i.e. nothing is listening)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def who_listens(port: int, show_args: bool = False) -> list[str] | None:
    """Return the pids that occupy a port (Windows netstat + tasklist style)."""
    try:
        out = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=5
        ).stdout
    except Exception:
        return None
    byp: list[str] = []
    for line in out.splitlines():
        if f":{port}" in line and "LISTENING" in line:
            byp.append(line.strip())
    return byp or None


def _rand_free() -> int:
    while True:
        p = random.randint(MIN_RANDOM, MAX_RANDOM)
        if port_free(p):
            return p


def scan_free(preferred: int, lo: int | None, hi: int | None) -> int | None:
    lo = lo or preferred
    hi = hi or preferred
    for p in range(lo, hi + 1):
        if p == preferred:
            continue
        if port_free(p):
            return p
    return None


@dataclass
class Allocation:
    service: str
    preferred: int
    actual: int
    host: str = "127.0.0.1"
    ts: float = field(default_factory=time.time)
    via: str = "preferred"

    def to_dict(self) -> dict[str, object]:
        return {
            "service": self.service,
            "preferred": self.preferred,
            "actual": self.actual,
            "host": self.host,
            "ts": self.ts,
            "via": self.via,
        }


class PortLedger:
    """Persistent, append-only, conflict-resolving port allocator."""

    def __init__(self, ledger: Path = DEFAULT_LEDGER, state: Path = DEFAULT_STATE):
        self.ledger = Path(ledger)
        self.state = Path(state)
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        self.state.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, rec: dict[str, object]) -> None:
        with self.ledger.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

    def current(self) -> dict[str, object]:
        """Load the latest advertised snapshot ({} if none yet)."""
        if self.state.exists():
            try:
                data: dict[str, object] = json.loads(
                    self.state.read_text(encoding="utf-8")
                )
                return data
            except json.JSONDecodeError:
                return {}
        return {}

    def _advertise(self, service: str, alloc: Allocation) -> None:
        current = self.current()
        current[service] = {
            "host": alloc.host,
            "port": alloc.actual,
            "via": alloc.via,
            "updated_at": alloc.ts,
        }
        self.state.write_text(json.dumps(current, indent=2), encoding="utf-8")

    def allocate(
        self,
        service: str,
        preferred: int,
        lo: int | None = None,
        hi: int | None = None,
        host: str = "127.0.0.1",
    ) -> Allocation:
        """Resolve and record a free port, preferring the requested one."""
        if port_free(preferred, host):
            via = "preferred"
        else:
            found = scan_free(preferred, lo, hi)
            if found is not None:
                preferred = found
                via = "scan"
            else:
                preferred = _rand_free()
                via = "random"
        alloc = Allocation(
            service=service, preferred=preferred, actual=preferred, host=host, via=via
        )
        rec = alloc.to_dict()
        who = who_listens(alloc.actual)
        if who:
            rec["prior_owner"] = who
        self._append(rec)
        self._advertise(service, alloc)
        return alloc

    def resolve(self, service: str) -> int | None:
        """Return the currently advertised port for a service (if any)."""
        entry = self.current().get(service)
        if not isinstance(entry, dict):
            return None
        port = entry.get("port")
        return port if isinstance(port, int) else None

    def status(self) -> list[dict[str, object]]:
        if not self.ledger.exists():
            return []
        rows = []
        for line in self.ledger.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            with contextlib.suppress(json.JSONDecodeError):
                rows.append(json.loads(line))
        return rows


def _cli() -> None:
    ap = argparse.ArgumentParser(prog="portledger", description=__doc__)
    ap.add_argument(
        "--version", "-V", action="store_true", help="print version and exit"
    )  # noqa: E501
    ap.add_argument("--service", "-s", help="service name, e.g. aioa")
    ap.add_argument("--preferred", type=int, default=11199, help="preferred port")
    ap.add_argument("--range", default=None, help="scan range lo-hi, e.g. 11190-11210")
    ap.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    ap.add_argument("--state", default=str(DEFAULT_STATE))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--status", action="store_true", help="print ledger history")
    ap.add_argument("--current", action="store_true", help="print advertised map")
    ap.add_argument("--who", type=int, help="show pids listening on a port")
    args = ap.parse_args()

    if args.version:
        print(f"portledger {__version__}")
        return

    pl = PortLedger(Path(args.ledger), Path(args.state))
    if args.status:
        print(json.dumps(pl.status(), indent=2))
        return
    if args.current:
        print(json.dumps(pl.current(), indent=2))
        return
    if args.who is not None:
        w = who_listens(args.who)
        print(w or f"no listener on {args.who}")
        return
    if not args.service:
        ap.error("provide --service (or --status/--current/--who-used)")
    lo = hi = None
    if args.range:
        lo, hi = (int(x) for x in args.range.split("-"))
    a = pl.allocate(args.service, args.preferred, lo, hi, args.host)
    print(json.dumps(a.to_dict(), indent=2))


if __name__ == "__main__":
    _cli()
