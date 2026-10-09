# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Workflow module — Mermaid-based graphical workflow authoring.

This module complements script writing by allowing users to define workflows as
Mermaid graphs, then execute them through the spine. It is intentionally
lightweight: no GUI dependency, no visual editor — just a well-structured,
versionable, and reviewable graph format that the CLI can render and validate.

The workflow format:

    nodes:
      - id: input
        label: User prompt
        type: input
      - id: context
        label: Assemble context
        type: action
        action: context.assemble
      - id: llm
        label: Run provider
        type: action
        action: provider.complete
      - id: verify
        label: Verify convergence
        type: gate
        gate: error_signal == 0
      - id: commit
        label: Commit to ledger
        type: action
        action: ledger.append

    edges:
      - from: input
        to: context
      - from: context
        to: llm
      - from: llm
        to: verify
      - from: verify
        to: commit

    profile: local
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class WorkflowNode:
    """A single node in a workflow graph."""

    id: str
    label: str
    type: str
    action: str = ""
    gate: str = ""


@dataclass
class WorkflowEdge:
    """A directed edge in a workflow graph."""

    from_node: str
    to_node: str


@dataclass
class Workflow:
    """A complete workflow definition."""

    name: str
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]
    profile: str = "local"
    description: str = ""

    def to_mermaid(self) -> str:
        """Render the workflow as a Mermaid graph."""
        lines = ["graph TD"]
        for node in self.nodes:
            label = node.label.replace('"', "'")
            node_type = node.type.replace('"', "'")
            action = node.action.replace('"', "'")
            gate = node.gate.replace('"', "'")

            node_label = label
            if action:
                node_label += f"<br/>[action: {action}]"
            if gate:
                node_label += f"<br/>[gate: {gate}]"

            node_id = node.id
            node_type_str = node_type
            lines.append(f"    {node_id}[{node_label}]")
            lines.append(
                f"    classDef {node_type_str} fill:#e8f1ff,"
                f"stroke:#2563eb,color:#1e3a8a"
            )
            lines.append(f"    class {node_id} {node_type_str}")

        for edge in self.edges:
            lines.append(f"    {edge.from_node} --> {edge.to_node}")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the workflow to a JSON-compatible dict."""
        return {
            "name": self.name,
            "description": self.description,
            "profile": self.profile,
            "nodes": [
                {
                    "id": node.id,
                    "label": node.label,
                    "type": node.type,
                    "action": node.action,
                    "gate": node.gate,
                }
                for node in self.nodes
            ],
            "edges": [
                {
                    "from": edge.from_node,
                    "to": edge.to_node,
                }
                for edge in self.edges
            ],
        }


def parse_workflow(data: dict[str, Any]) -> Workflow:
    """Parse a workflow definition from a dict."""
    name = data.get("name", "workflow")
    nodes = [
        WorkflowNode(
            id=str(node["id"]),
            label=str(node["label"]),
            type=str(node["type"]),
            action=str(node.get("action", "")),
            gate=str(node.get("gate", "")),
        )
        for node in data.get("nodes", [])
    ]
    edges = [
        WorkflowEdge(
            from_node=str(edge["from"]),
            to_node=str(edge["to"]),
        )
        for edge in data.get("edges", [])
    ]

    # Validate: every edge references existing nodes
    node_ids = {node.id for node in nodes}
    for edge in edges:
        if edge.from_node not in node_ids:
            raise ValueError(f"Edge from '{edge.from_node}' references unknown node")
        if edge.to_node not in node_ids:
            raise ValueError(f"Edge to '{edge.to_node}' references unknown node")

    return Workflow(
        name=name,
        nodes=nodes,
        edges=edges,
        profile=str(data.get("profile", "local")),
        description=str(data.get("description", "")),
    )


def load_workflow(path: str | Path) -> Workflow:
    """Load a workflow definition from a JSON or YAML file."""
    import json

    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        if path.suffix == ".yaml" or path.suffix == ".yml":
            import yaml

            data = yaml.safe_load(f)
        else:
            data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("Workflow file must contain a mapping")

    return parse_workflow(data)


def save_workflow(workflow: Workflow, path: str | Path) -> None:
    """Save the workflow to a JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(workflow.to_dict(), f, indent=2)


def generate_mermaid(workflow: Workflow) -> str:
    """Return the Mermaid graph text for a workflow."""
    return f"```mermaid\n{workflow.to_mermaid()}\n```"


def validate_workflow(workflow: Workflow) -> list[str]:
    """Validate workflow structure and return errors (empty if valid)."""
    errors: list[str] = []

    node_ids = [node.id for node in workflow.nodes]
    if len(node_ids) != len(set(node_ids)):
        errors.append("Duplicate node IDs")

    if not workflow.nodes:
        errors.append("Workflow must have at least one node")

    for node in workflow.nodes:
        if node.type not in {"input", "action", "gate", "output"}:
            errors.append(f"Node '{node.id}' has unknown type '{node.type}'")
        if node.type == "action" and not node.action:
            errors.append(f"Action node '{node.id}' requires an action")
        if node.type == "gate" and not node.gate:
            errors.append(f"Gate node '{node.id}' requires a gate condition")

    if workflow.nodes and not errors:
        try:
            topological_order(workflow)
        except ValueError as e:
            errors.append(str(e))

    return errors


def topological_order(workflow: Workflow) -> list[WorkflowNode]:
    """Return nodes in dependency (topological) order.

    Raises ValueError naming the cycle when the graph cannot be
    ordered — execution and validation both depend on this, and the
    authoring-only version of this module never checked for cycles.
    """
    indegree: dict[str, int] = {node.id: 0 for node in workflow.nodes}
    outgoing: dict[str, list[str]] = {node.id: [] for node in workflow.nodes}
    for edge in workflow.edges:
        outgoing[edge.from_node].append(edge.to_node)
        indegree[edge.to_node] += 1
    queue = sorted(nid for nid, deg in indegree.items() if deg == 0)
    by_id = {node.id: node for node in workflow.nodes}
    ordered: list[WorkflowNode] = []
    while queue:
        nid = queue.pop(0)
        ordered.append(by_id[nid])
        for nxt in sorted(outgoing[nid]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
                queue.sort()
    if len(ordered) != len(workflow.nodes):
        stuck = sorted(set(indegree) - {n.id for n in ordered})
        raise ValueError(f"Workflow graph has a cycle involving: {stuck}")
    return ordered


_GATE_OPS = ("==", "!=", "<=", ">=", "<", ">")


def _eval_gate(expression: str, state: dict[str, Any]) -> bool:
    """Evaluate a gate expression of the form ``<key> <op> <number>``.

    Deliberately a tiny, safe subset (no eval): the left side is a state
    key, the right side a numeric literal. Unknown shapes raise
    ValueError rather than guessing.
    """
    for op in _GATE_OPS:
        if op in expression:
            left, _, right = expression.partition(op)
            key = left.strip()
            if key not in state:
                raise ValueError(f"Gate references unknown state key '{key}'")
            actual = float(state[key])
            target = float(right.strip())
            if op == "==":
                return actual == target
            if op == "!=":
                return actual != target
            if op == "<=":
                return actual <= target
            if op == ">=":
                return actual >= target
            if op == "<":
                return actual < target
            return actual > target
    raise ValueError(f"Unsupported gate expression: {expression!r}")


@dataclass
class WorkflowRun:
    """The record of one workflow execution."""

    order: list[str]
    outputs: dict[str, Any]
    status: str  # "completed" | "gate_failed" | "action_failed"
    failed_node: str = ""
    error: str = ""


def execute_workflow(
    workflow: Workflow,
    handlers: dict[str, Any],
    initial_state: dict[str, Any] | None = None,
) -> WorkflowRun:
    """Execute a workflow: nodes in topological order, gates enforced.

    ``handlers`` maps an action string (e.g. ``provider.complete``) to a
    callable ``handler(node, state) -> value``; the value is stored in
    state under the node's id and in the run's outputs. Gate nodes
    evaluate their expression against state — a failed gate stops the
    run with status ``gate_failed`` (the spine's semantics: a gate that
    fails blocks everything downstream, exactly as the gated cycle
    blocks a commit). Input/output nodes pass state through.
    """
    state: dict[str, Any] = dict(initial_state or {})
    outputs: dict[str, Any] = {}
    order: list[str] = []
    for node in topological_order(workflow):
        order.append(node.id)
        if node.type == "gate":
            try:
                passed = _eval_gate(node.gate, state)
            except ValueError as e:
                return WorkflowRun(order, outputs, "action_failed", node.id, str(e))
            outputs[node.id] = {"gate": node.gate, "passed": passed}
            if not passed:
                return WorkflowRun(order, outputs, "gate_failed", node.id)
        elif node.type == "action":
            handler = handlers.get(node.action)
            if handler is None:
                return WorkflowRun(
                    order,
                    outputs,
                    "action_failed",
                    node.id,
                    f"No handler registered for action '{node.action}'",
                )
            try:
                value = handler(node, state)
            except Exception as e:  # handler failures are run data
                return WorkflowRun(
                    order, outputs, "action_failed", node.id, f"{type(e).__name__}: {e}"
                )
            state[node.id] = value
            outputs[node.id] = value
        else:  # input / output nodes pass through
            outputs[node.id] = state.get(node.id)
    return WorkflowRun(order, outputs, "completed")


def build_default_handlers(
    *,
    store: Any = None,
    provider: Any = None,
    ledger: Any = None,
) -> dict[str, Any]:
    """Real handlers for the standard template's actions.

    - ``context.assemble`` renders the store's in-scope snapshot.
    - ``provider.complete`` runs the provider on the run's input and
      publishes its ``error_signal`` into state, which is what the
      template's gate (``error_signal == 0``) reads. With no reachable
      provider it reports error_signal 1.0 — the gate then blocks the
      commit, which is the spine working as designed, not a fake pass.
    - ``ledger.append`` writes a real CTST record and returns its hash.
    """

    def _assemble(node: WorkflowNode, state: dict[str, Any]) -> str:
        if store is None:
            return ""
        from ..context import ContextScope
        from ..store import snapshot_for_prompt

        return snapshot_for_prompt(store, ContextScope.SESSION)

    def _complete(node: WorkflowNode, state: dict[str, Any]) -> float:
        if provider is None:
            state["error_signal"] = 1.0
            return 1.0
        result = provider.complete(
            prompt=str(state.get("input", "")),
            context=[],
            max_tokens=512,
            temperature=0.0,
        )
        state["error_signal"] = float(result.error_signal)
        state["output"] = result.output
        return float(result.error_signal)

    def _append(node: WorkflowNode, state: dict[str, Any]) -> str:
        if ledger is None:
            return ""
        from ..ctst import CTSTRecord

        record = CTSTRecord(
            intent={"summary": str(state.get("input", ""))},
            mechanism="workflow",
            outcome={"output": state.get("output", "")},
            error_signal=float(state.get("error_signal", 1.0)),
            committed=True,
        )
        return str(ledger.append(record))

    return {
        "context.assemble": _assemble,
        "provider.complete": _complete,
        "ledger.append": _append,
    }


def workflow_from_template(name: str, profile: str = "local") -> Workflow:
    """Generate a standard transform workflow template."""
    return Workflow(
        name=name,
        nodes=[
            WorkflowNode(
                id="input",
                label="User prompt",
                type="input",
            ),
            WorkflowNode(
                id="context",
                label="Assemble context",
                type="action",
                action="context.assemble",
            ),
            WorkflowNode(
                id="provider",
                label="Run provider",
                type="action",
                action="provider.complete",
            ),
            WorkflowNode(
                id="verify",
                label="Verify convergence",
                type="gate",
                gate="error_signal == 0",
            ),
            WorkflowNode(
                id="commit",
                label="Commit to ledger",
                type="action",
                action="ledger.append",
            ),
            WorkflowNode(
                id="output",
                label="Return output",
                type="output",
            ),
        ],
        edges=[
            WorkflowEdge(from_node="input", to_node="context"),
            WorkflowEdge(from_node="context", to_node="provider"),
            WorkflowEdge(from_node="provider", to_node="verify"),
            WorkflowEdge(from_node="verify", to_node="commit"),
            WorkflowEdge(from_node="commit", to_node="output"),
        ],
        profile=profile,
        description="Standard provider transform workflow",
    )


def main() -> None:
    """CLI entrypoint for workflow operations."""
    parser = argparse.ArgumentParser(
        prog="spine workflow",
        description="Manage Mermaid-based workflows",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    init_parser = subparsers.add_parser("init", help="Create a new workflow")
    init_parser.add_argument("--name", type=str, required=True, help="Workflow name")
    init_parser.add_argument("--profile", type=str, default="local", help="Profile")
    init_parser.add_argument("--output", type=str, default=None, help="Output file")

    # list
    subparsers.add_parser("list", help="List available workflows")

    # show
    show_parser = subparsers.add_parser("show", help="Show workflow as Mermaid")
    show_parser.add_argument("file", type=str, help="Workflow file")

    args = parser.parse_args()

    if args.command == "init":
        wf = workflow_from_template(args.name, args.profile)
        output = args.output or f"{args.name}.json"
        save_workflow(wf, output)
        print(f"Created workflow '{args.name}' at {output}")
        print(f"Mermaid preview:\n{generate_mermaid(wf)}")

    elif args.command == "list":
        print("Available workflows:")
        for p in Path(".").glob("*.json"):
            try:
                wf = load_workflow(p)
                print(f"  {p.name}: {wf.name} (profile: {wf.profile})")
            except Exception:
                pass

    elif args.command == "show":
        wf = load_workflow(args.file)
        errors = validate_workflow(wf)
        if errors:
            print("Validation errors:")
            for e in errors:
                print(f"  - {e}")
        else:
            print(generate_mermaid(wf))


if __name__ == "__main__":
    main()
