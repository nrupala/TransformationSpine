# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: Apache-2.0
r"""CTST ledger — Context-Tracked State Transition durable journal.

Ported from the OCS repos' concepts (D:\ocs-software, D:\ocscoder) but
implemented fresh for the TransformationSpine stack. The CTST ledger is
the immutable record of every transformation attempt, enabling:

* Lineage (provenance DAG) — why a fact exists
* Audit trail — every action recorded, never rewritten
* Convergence measurement — gap/error signal per transition
* Rollback — last committed checkpoint is the rollback unit

Schema mirrors the OCS CTST:
  id, timestamp, origin_state, intent, drivers, constraints,
  context, mechanism, mechanism_version, outcome, assessment,
  lineage_parents, next_cycle
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass
class CTSTRecord:
    """One immutable transformation attempt in the ledger."""

    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    origin_state: dict[str, Any] = field(default_factory=dict)
    intent: dict[str, Any] = field(default_factory=dict)
    drivers: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    mechanism: str = ""
    mechanism_version: str = ""
    outcome: dict[str, Any] = field(default_factory=dict)
    assessment: dict[str, Any] = field(default_factory=dict)
    lineage_parents: list[str] = field(default_factory=list)
    next_cycle: str | None = None
    error_signal: float = 1.0
    committed: bool = False
    telemetry: dict[str, Any] = field(default_factory=dict)
    # Hash-chain fields, assigned by CTSTLedger.append() and persisted in
    # the JSONL line so the chain survives process restarts. Empty for
    # records that have not been appended yet (and for legacy lines written
    # before hashes were persisted).
    prev_hash: str = ""
    record_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "origin_state": self.origin_state,
            "intent": self.intent,
            "drivers": self.drivers,
            "constraints": self.constraints,
            "context": self.context,
            "mechanism": self.mechanism,
            "mechanism_version": self.mechanism_version,
            "outcome": self.outcome,
            "assessment": self.assessment,
            "lineage_parents": self.lineage_parents,
            "next_cycle": self.next_cycle,
            "error_signal": self.error_signal,
            "committed": self.committed,
            "telemetry": self.telemetry,
            "prev_hash": self.prev_hash,
            "record_hash": self.record_hash,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> CTSTRecord:
        ts = datetime.fromisoformat(data["timestamp"])
        return CTSTRecord(
            id=data["id"],
            timestamp=ts,
            origin_state=data.get("origin_state", {}),
            intent=data.get("intent", {}),
            drivers=data.get("drivers", []),
            constraints=data.get("constraints", []),
            context=data.get("context", {}),
            mechanism=data.get("mechanism", ""),
            mechanism_version=data.get("mechanism_version", ""),
            outcome=data.get("outcome", {}),
            assessment=data.get("assessment", {}),
            lineage_parents=data.get("lineage_parents", []),
            next_cycle=data.get("next_cycle"),
            error_signal=data.get("error_signal", 1.0),
            committed=data.get("committed", False),
            telemetry=data.get("telemetry", {}),
            prev_hash=data.get("prev_hash", ""),
            record_hash=data.get("record_hash", ""),
        )


class CTSTLedger:
    """Append-only CTST journal with hash-chain tamper evidence.

    Storage: JSONL — one record per line, daily-partitioned files.
    Integrity: each record's hash includes the previous record's hash,
    forming a chain. Any tampering breaks the chain.
    """

    def __init__(self, root: str | Path | None = None) -> None:
        if root is None:
            root = os.environ.get("SPINE_CTST_ROOT", "ledger")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._chain: list[str] = []  # hash chain for integrity
        self._rebuild_chain()

    def _file_path(self, date: datetime | None = None) -> Path:
        d = date or datetime.now(UTC)
        return self.root / f"ctst_{d.strftime('%Y-%m-%d')}.jsonl"

    def _hash_record(self, record: CTSTRecord, prev_hash: str = "") -> str:
        """Compute SHA-256 hash of a record including previous hash.

        The hash fields themselves are excluded from the payload; the
        previous hash enters as ``_prev_hash`` so a record's hash binds
        both its content and its position in the chain.
        """
        data = record.to_dict()
        data.pop("prev_hash", None)
        data.pop("record_hash", None)
        data["_prev_hash"] = prev_hash
        payload = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    def _iter_lines(self) -> Any:
        """Yield (file_path, parsed dict) for every stored line, in order."""
        for file_path in sorted(self.root.glob("ctst_*.jsonl")):
            with open(file_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        yield file_path, json.loads(line)

    def _rebuild_chain(self) -> None:
        """Rebuild the in-memory chain head from what is stored on disk.

        Lines written by this version carry their hash; legacy lines
        (written before hashes were persisted) are folded into the chain
        by computing their chained hash, so appends after a restart
        continue the same chain instead of restarting it.
        """
        self._chain = []
        prev_hash = ""
        for _path, data in self._iter_lines():
            stored = data.get("record_hash", "")
            if stored:
                prev_hash = stored
            else:
                prev_hash = self._hash_record(CTSTRecord.from_dict(data), prev_hash)
            self._chain.append(prev_hash)

    def append(self, record: CTSTRecord) -> str:
        """Append a CTST record to the ledger. Returns the record's hash.

        The record's ``prev_hash``/``record_hash`` are set on the record
        and persisted in the JSONL line, so the chain is verifiable from
        disk alone, in any later process.
        """
        prev_hash = self._chain[-1] if self._chain else ""
        record_hash = self._hash_record(record, prev_hash)
        record.prev_hash = prev_hash
        record.record_hash = record_hash
        file_path = self._file_path()

        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict(), default=str) + "\n")

        self._chain.append(record_hash)
        return record_hash

    @property
    def head_hash(self) -> str:
        """Hash of the most recent record in the chain ("" if empty)."""
        return self._chain[-1] if self._chain else ""

    def read(self, date: datetime | None = None) -> list[CTSTRecord]:
        """Read all records from a day's ledger (default: today)."""
        file_path = self._file_path(date)
        if not file_path.exists():
            return []

        records: list[CTSTRecord] = []
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(CTSTRecord.from_dict(json.loads(line)))
        return records

    def query(
        self,
        mechanism: str | None = None,
        committed_only: bool = False,
        since: datetime | None = None,
    ) -> list[CTSTRecord]:
        """Query ledger with filters. Reads all files and filters."""
        records: list[CTSTRecord] = []
        for file_path in sorted(self.root.glob("ctst_*.jsonl")):
            records.extend(
                self.read(
                    date=datetime.strptime(
                        file_path.stem.replace("ctst_", ""), "%Y-%m-%d"
                    )
                )
            )

        if mechanism:
            records = [r for r in records if r.mechanism == mechanism]
        if committed_only:
            records = [r for r in records if r.committed]
        if since:
            records = [r for r in records if r.timestamp >= since]
        return records

    def verify_chain(self) -> bool:
        """Verify the hash chain integrity from disk. True iff unbroken.

        Every line is checked, in file/date order:
        - a line carrying hashes must name the running chain head as its
          ``prev_hash``, and its stored ``record_hash`` must equal the
          hash recomputed from its content plus that prev_hash. Any edit
          to a stored record — content, hashes, order, or deletion of a
          non-final line — fails this check.
        - a legacy line (written before hashes were persisted) carries no
          stored hash to check against; it is folded into the running
          chain by computation and verification continues. Legacy lines
          are therefore covered only transitively, through the stored
          hashes of the records that follow them.
        """
        prev_hash = ""
        for _path, data in self._iter_lines():
            stored_prev = data.get("prev_hash", "")
            stored_hash = data.get("record_hash", "")
            record = CTSTRecord.from_dict(data)
            if stored_hash:
                if stored_prev != prev_hash:
                    return False
                if self._hash_record(record, prev_hash) != stored_hash:
                    return False
                prev_hash = stored_hash
            else:
                prev_hash = self._hash_record(record, prev_hash)
        return True

    def lineage(self, record_id: str) -> list[CTSTRecord]:
        """Return the full lineage chain for a record (parents → child)."""
        all_records = []
        for file_path in sorted(self.root.glob("ctst_*.jsonl")):
            all_records.extend(
                self.read(
                    date=datetime.strptime(
                        file_path.stem.replace("ctst_", ""), "%Y-%m-%d"
                    )
                )
            )

        by_id: dict[str, CTSTRecord] = {r.id: r for r in all_records}
        lineage: list[CTSTRecord] = []
        current_id = record_id
        while current_id in by_id:
            record = by_id[current_id]
            lineage.append(record)
            if not record.lineage_parents:
                break
            current_id = record.lineage_parents[-1]
        return list(reversed(lineage))

    def last_committed(self) -> CTSTRecord | None:
        """Return the last committed record (rollback checkpoint)."""
        committed = [r for r in self.read() if r.committed]
        return max(committed, key=lambda r: r.timestamp) if committed else None
