# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Agent-protocol surfaces: A2A and ACP, over the same gated cycle.

The spine serves three kinds of callers, and these are the agent ones
(the program surfaces are the REST API + CLI; agents additionally get
MCP in ``spine.mcp_server``):

- **A2A** (Agent2Agent): an agent card at
  ``/.well-known/agent-card.json`` for discovery, and a JSON-RPC
  endpoint (``POST /a2a``) implementing ``message/send`` and
  ``tasks/get``. A message's text part becomes a transform intent; the
  cycle runs synchronously and the Task completes with the output as
  an artifact.
- **ACP** (Agent Communication Protocol): REST agent manifests
  (``GET /acp/agents``) and runs (``POST /acp/agents/{name}/runs``,
  ``GET .../runs/{id}``). Runs execute synchronously against the same
  cycle; run records are kept in memory for status reads.

Both are thin protocol adapters: every run goes through the injected
transform callable, which is the spine's one gated cycle — same
planner, gates, ledger, and telemetry as the REST API.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

TransformFn = Callable[..., dict[str, Any]]

AGENT_NAME = "transformationspine"
AGENT_DESCRIPTION = (
    "Provider-neutral transformation spine: gated LLM cycles over a "
    "scoped, provenance-tracked context store, with a tamper-evident "
    "CTST ledger, caller-side gate evaluation, and a token-efficiency "
    "engine. Serves agents (MCP, A2A, ACP), humans (browser UI, CLI), "
    "and programs (REST API)."
)


def build_agent_card(version: str) -> dict[str, Any]:
    """A2A agent card (discovery document)."""
    return {
        "protocolVersion": "0.3.0",
        "name": AGENT_NAME,
        "description": AGENT_DESCRIPTION,
        "url": "/a2a",
        "version": version,
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [
            {
                "id": "transform",
                "name": "Gated transformation cycle",
                "description": (
                    "Submit an intent; the spine assembles scoped context "
                    "under a token plan, runs the provider, evaluates "
                    "gates, and records the cycle in the CTST ledger."
                ),
                "tags": ["llm", "context", "orchestration"],
            },
            {
                "id": "connectors",
                "name": "Connector tools",
                "description": (
                    "Execute tools on discovered connectors (GitHub, "
                    "Jira, ServiceNow, Azure DevOps, Databricks, "
                    "Confluence, plus plugins) via MCP or the REST API."
                ),
                "tags": ["tools", "connectors"],
            },
        ],
    }


def _text_of_parts(parts: list[dict[str, Any]]) -> str:
    texts = [
        str(p.get("text", ""))
        for p in parts
        if isinstance(p, dict) and p.get("kind", "text") == "text"
    ]
    return "\n".join(t for t in texts if t)


@dataclass
class A2AAgent:
    """A2A JSON-RPC handler (message/send, tasks/get)."""

    transform: TransformFn
    version: str = "0.2.0"
    tasks: dict[str, dict[str, Any]] = field(default_factory=dict)

    def card(self) -> dict[str, Any]:
        return build_agent_card(self.version)

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params") or {}
        if req_id is None:
            return None
        if method == "message/send":
            return self._ok(req_id, self._send(params))
        if method == "tasks/get":
            task = self.tasks.get(str(params.get("id", "")))
            if task is None:
                return self._err(req_id, -32001, "Task not found")
            return self._ok(req_id, task)
        return self._err(req_id, -32601, f"Method not found: {method}")

    def _send(self, params: dict[str, Any]) -> dict[str, Any]:
        message = params.get("message") or {}
        intent = _text_of_parts(list(message.get("parts") or []))
        metadata = dict(message.get("metadata") or {})
        task_id = str(uuid.uuid4())
        context_id = str(message.get("contextId") or uuid.uuid4())
        if not intent:
            task = self._task(task_id, context_id, "failed", "empty intent")
            self.tasks[task_id] = task
            return task
        try:
            result = self.transform(
                intent=intent,
                provider=str(metadata.get("provider", "llama.cpp")),
                scope=str(metadata.get("scope", "SESSION")),
            )
            task = self._task(
                task_id,
                context_id,
                "completed",
                str(result.get("output", "")),
            )
            task["metadata"] = {
                "verdict": result.get("verdict"),
                "error_signal": result.get("error_signal"),
                "committed": result.get("committed"),
            }
        except Exception as e:
            task = self._task(task_id, context_id, "failed", f"{type(e).__name__}: {e}")
        self.tasks[task_id] = task
        return task

    @staticmethod
    def _task(task_id: str, context_id: str, state: str, text: str) -> dict[str, Any]:
        return {
            "id": task_id,
            "contextId": context_id,
            "status": {"state": state},
            "artifacts": [
                {
                    "artifactId": f"{task_id}-output",
                    "parts": [{"kind": "text", "text": text}],
                }
            ],
        }

    @staticmethod
    def _ok(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    @staticmethod
    def _err(req_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }


@dataclass
class ACPAgent:
    """ACP REST runs over the gated cycle (synchronous execution)."""

    transform: TransformFn
    version: str = "0.2.0"
    runs: dict[str, dict[str, Any]] = field(default_factory=dict)

    def manifest(self) -> dict[str, Any]:
        return {
            "name": AGENT_NAME,
            "description": AGENT_DESCRIPTION,
            "version": self.version,
            "input": {"type": "text/plain"},
            "output": {"type": "text/plain"},
        }

    def create_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        intent = self._intent_of(payload)
        run_id = str(uuid.uuid4())
        run: dict[str, Any] = {
            "run_id": run_id,
            "agent": AGENT_NAME,
            "created_at": time.time(),
            "status": "completed",
            "output": [],
        }
        if not intent:
            run["status"] = "failed"
            run["error"] = "empty intent: provide 'input' text"
            self.runs[run_id] = run
            return run
        try:
            result = self.transform(
                intent=intent,
                provider=str(payload.get("provider", "llama.cpp")),
                scope=str(payload.get("scope", "SESSION")),
            )
            run["output"] = [
                {
                    "type": "text/plain",
                    "content": str(result.get("output", "")),
                }
            ]
            run["verdict"] = result.get("verdict")
        except Exception as e:
            run["status"] = "failed"
            run["error"] = f"{type(e).__name__}: {e}"
        self.runs[run_id] = run
        return run

    @staticmethod
    def _intent_of(payload: dict[str, Any]) -> str:
        raw = payload.get("input", payload.get("intent", ""))
        if isinstance(raw, str):
            return raw
        if isinstance(raw, list):  # ACP-style message parts
            texts: list[str] = []
            for item in raw:
                if isinstance(item, dict):
                    parts = item.get("parts") or []
                    for part in parts:
                        if isinstance(part, dict) and part.get("content"):
                            texts.append(str(part["content"]))
            return "\n".join(texts)
        return ""
