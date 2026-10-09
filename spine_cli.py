# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
#!/usr/bin/env python3
"""Entrypoint script for the TransformationSpine command-line interface.

Provides CLI commands:
  spine --help
  spine status
  spine context
  spine transform <intent> [--profile <name>]
  spine provider <name>
  spine ledger
  spine telemetry
  spine workflow init --name <name> [--profile <name>]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import httpx
import yaml

from spine import ContextStore

# Global spine instances (shared across CLI commands)
_spine_app = None
_spine_store: ContextStore | None = None
_spine_providers: dict[str, Any] = {}
_profile: str = "local"


def load_env_config(profile: str = "local") -> None:
    """Load the providers a profile declares, via the spine factory.

    The profile genuinely selects: local builds the llama.cpp route,
    cloud builds OpenAI/Anthropic/HuggingFace (skipping any whose API
    key is unset), hybrid builds both local and cloud primaries.
    (Previously this iterated profile names as if they were provider
    names and loaded nothing at all.)
    """
    config_path = Path("Providers.yaml")
    if not config_path.exists():
        return

    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    from spine.factory import build_provider_map

    global _spine_providers
    _spine_providers = build_provider_map(profile, data)
    for name in _spine_providers:
        print(f"Loaded provider: {name} (profile={profile})")


def load_routing_config(profile: str = "local") -> dict[str, Any]:
    """Load routing configuration from Routing.yaml."""
    config_path = Path("Routing.yaml")
    if not config_path.exists():
        return {"routes": {}}
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {"routes": {}}


def do_status() -> None:
    """Execute the status command."""
    try:
        resp = httpx.get("http://127.0.0.1:8000/api/v1/status", timeout=5.0)
        if resp.status_code == 200:
            print(json.dumps(resp.json(), indent=2))
        else:
            print(f"Status request failed: {resp.status_code}")
    except Exception as e:
        print(f"Could not get status: {e}")


def do_context() -> None:
    """Execute the context command."""
    try:
        resp = httpx.get("http://127.0.0.1:8000/api/v1/context", timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            print(data.get("context", "# No context available"))
        else:
            print(f"Context request failed: {resp.status_code}")
    except Exception as e:
        print(f"Could not get context: {e}")


def do_transform(intent: str, provider: str, scope: str, profile: str) -> None:
    """Execute the transform command."""
    # The profile selects the provider through Routing.yaml when the
    # caller left the provider at its default: e.g. --profile cloud
    # routes the coding task to the cloud primary instead of llama.cpp.
    if provider == "llama.cpp" and profile != "local":
        routing = load_routing_config(profile)
        from spine.factory import select_for_task
        from spine.provider import RouterRule

        rules = RouterRule.from_yaml(routing, profile=profile)
        rule = select_for_task(rules, "coding")
        if rule is not None and rule.primary_provider:
            from spine.factory import canonical_provider

            provider = canonical_provider(rule.primary_provider)
            print(
                f"Profile '{profile}' routes coding -> {provider} "
                f"({rule.primary_model})"
            )

    try:
        resp = httpx.post(
            "http://127.0.0.1:8000/api/v1/transform",
            json={"intent": intent, "provider": provider, "scope": scope},
            timeout=30.0,
        )
        if resp.status_code == 200:
            result = resp.json()
            print(json.dumps(result, indent=2))
        else:
            print(f"Transform failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Transform request error: {e}")


def do_ledger(verify: bool = False) -> None:
    """Execute the ledger command."""
    if verify:
        try:
            resp = httpx.get("http://127.0.0.1:8000/api/v1/ledger/verify", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                state = "VALID" if data["valid"] else "INVALID — chain broken"
                print(f"CTST ledger chain: {state}")
                print(f"Records: {data['records']}  Head: {data['head_hash'][:16]}")
            else:
                print(f"Ledger verify failed: {resp.status_code}")
        except Exception as e:
            print(f"Ledger verify error: {e}")
        return
    try:
        resp = httpx.get("http://127.0.0.1:8000/api/v1/ledger", timeout=5.0)
        if resp.status_code == 200:
            ledger_data = resp.json()
            print(json.dumps(ledger_data, indent=2))
        else:
            print(f"Ledger request failed: {resp.status_code}")
    except Exception as e:
        print(f"Ledger request error: {e}")


def do_telemetry() -> None:
    """Execute the telemetry command."""
    try:
        resp = httpx.get("http://127.0.0.1:8000/api/v1/telemetry", timeout=5.0)
        if resp.status_code == 200:
            telemetry_data = resp.json()
            print(json.dumps(telemetry_data, indent=2))
        else:
            print(f"Telemetry request failed: {resp.status_code}")
    except Exception as e:
        print(f"Telemetry request error: {e}")


def do_connector_list() -> None:
    """List discovered connectors via the API."""
    try:
        resp = httpx.get("http://127.0.0.1:8000/api/v1/connectors", timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            for conn in data["connectors"]:
                caps = ", ".join(conn["capabilities"])
                print(f"  {conn['name']} [{conn['source']}] tools: {caps}")
            for err in data.get("discovery_errors", []):
                print(f"  discovery error: {err}")
        else:
            print(f"Connector request failed: {resp.status_code}")
    except Exception as e:
        print(f"Connector request error: {e}")


def do_connector_execute(name: str, tool: str, params_json: str) -> None:
    """Execute one connector tool via the API."""
    try:
        params = json.loads(params_json) if params_json else {}
    except json.JSONDecodeError as e:
        print(f"Invalid --params JSON: {e}")
        return
    try:
        resp = httpx.post(
            f"http://127.0.0.1:8000/api/v1/connectors/{name}/execute",
            json={"tool": tool, "params": params},
            timeout=30.0,
        )
        print(json.dumps(resp.json(), indent=2, default=str))
    except Exception as e:
        print(f"Connector execute error: {e}")


def do_mcp() -> None:
    """Serve the spine to agents over MCP on stdio (subprocess pattern).

    Initializes the same state as the API lifespan, then speaks
    line-delimited JSON-RPC until stdin closes.
    """
    import spine.api as api_module
    from spine.mcp_server import serve_stdio

    api_module._init_state()
    try:
        serve_stdio(api_module.build_mcp_server())
    finally:
        api_module._teardown_state()


def do_workflow_init(name: str, profile: str, output: str | None) -> None:
    """Execute the workflow init command."""
    from spine.workflow import (
        generate_mermaid,
        save_workflow,
        workflow_from_template,
    )

    wf = workflow_from_template(name, profile)
    output_file = output or f"{name}.json"
    save_workflow(wf, output_file)
    # The documented deliverable is the validated Mermaid file; write it
    # alongside the JSON definition (previously only JSON was produced).
    mmd_file = f"{name}.mmd"
    Path(mmd_file).write_text(generate_mermaid(wf), encoding="utf-8")
    print(f"Created workflow '{name}' at {output_file} and {mmd_file}")
    print(f"Provider: {profile}")
    print("\nMermaid preview:")
    print(generate_mermaid(wf))


def do_workflow_run(file: str, intent: str) -> None:
    """Execute a workflow file through the spine's workflow engine."""
    from spine.ctst import CTSTLedger
    from spine.store import ContextStore
    from spine.workflow import (
        build_default_handlers,
        execute_workflow,
        load_workflow,
        validate_workflow,
    )

    wf = load_workflow(file)
    errors = validate_workflow(wf)
    if errors:
        print("Workflow is invalid:")
        for e in errors:
            print(f"  - {e}")
        return

    provider = None
    load_env_config(_profile)
    candidate = _spine_providers.get("llama.cpp")
    if candidate is not None:
        try:
            if candidate.list_models():
                provider = candidate
        except Exception:
            provider = None

    handlers = build_default_handlers(
        store=ContextStore(),
        provider=provider,
        ledger=CTSTLedger(),
    )
    run = execute_workflow(wf, handlers, initial_state={"input": intent})
    print(f"Workflow '{wf.name}': {run.status}")
    print(f"Order: {' -> '.join(run.order)}")
    if run.failed_node:
        print(f"Stopped at: {run.failed_node} {run.error}")
    print(json.dumps(run.outputs, indent=2, default=str))


def do_provider_list() -> None:
    """Execute the provider list command."""
    load_env_config(_profile)
    print("Available providers:")
    for name in _spine_providers:
        print(f"  {name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="spine",
        description="Transformation Spine CLI and API",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default="local",
        choices=["local", "cloud", "hybrid"],
        help="Profile for provider selection (default: local)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to run the API server on (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run the API server on (default: 8000)",
    )
    parser.add_argument(
        "--no-server",
        action="store_true",
        help="Run CLI commands only, do not start the API server",
    )

    subparsers = parser.add_subparsers(dest="command", required=False)

    # spine status
    subparsers.add_parser("status", help="Show spine status")

    # spine context
    subparsers.add_parser("context", help="Render current in-scope context")

    # spine ledger
    ledger_parser = subparsers.add_parser("ledger", help="Read CTST ledger entries")
    ledger_parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify the CTST hash chain instead of listing entries",
    )

    # spine telemetry
    subparsers.add_parser("telemetry", help="Show aggregated telemetry metrics")

    # spine mcp
    subparsers.add_parser("mcp", help="Serve the spine over MCP (stdio)")

    # spine connector
    connector_parser = subparsers.add_parser(
        "connector", help="Connector discovery and execution"
    )
    connector_sub = connector_parser.add_subparsers(
        dest="connector_command", required=True
    )
    connector_sub.add_parser("list", help="List discovered connectors")
    exec_parser = connector_sub.add_parser("execute", help="Execute a connector tool")
    exec_parser.add_argument("name", type=str, help="Connector name")
    exec_parser.add_argument("tool", type=str, help="Tool name")
    exec_parser.add_argument(
        "--params", type=str, default="{}", help="Tool params as JSON"
    )

    # spine transform
    transform_parser = subparsers.add_parser(
        "transform", help="Submit a transformation intent"
    )
    transform_parser.add_argument(
        "intent",
        type=str,
        help="Transformation intent (what to accomplish)",
    )
    transform_parser.add_argument(
        "--provider",
        type=str,
        default="llama.cpp",
        help="Provider to use (default: llama.cpp)",
    )
    transform_parser.add_argument(
        "--scope",
        type=str,
        default="SESSION",
        help="Context scope to use (default: SESSION)",
    )

    # spine provider command
    provider_parser = subparsers.add_parser(
        "provider", help="Provider operations and listing"
    )
    provider_sub = provider_parser.add_subparsers(
        dest="provider_command", required=True
    )
    provider_sub.add_parser("list", help="List available providers")

    # spine workflow
    workflow_parser = subparsers.add_parser(
        "workflow", help="Manage Mermaid-based workflows"
    )
    workflow_sub = workflow_parser.add_subparsers(
        dest="workflow_command", required=True
    )

    init_parser = workflow_sub.add_parser("init", help="Create a new workflow")
    init_parser.add_argument("--name", type=str, required=True, help="Workflow name")
    init_parser.add_argument(
        "--profile",
        type=str,
        default="local",
        help="Profile for the workflow (default: local)",
    )
    init_parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path (default: <name>.json)",
    )

    run_parser = workflow_sub.add_parser("run", help="Execute a workflow file")
    run_parser.add_argument("file", type=str, help="Workflow JSON/YAML file")
    run_parser.add_argument(
        "--intent",
        type=str,
        default="",
        help="Input intent for the workflow's provider step",
    )

    args = parser.parse_args()

    # Set global profile
    _profile = args.profile

    # Handle top-level commands
    if args.command == "status":
        do_status()
    elif args.command == "context":
        do_context()
    elif args.command == "ledger":
        do_ledger(verify=args.verify)
    elif args.command == "telemetry":
        do_telemetry()
    elif args.command == "mcp":
        do_mcp()
    elif args.command == "connector":
        if args.connector_command == "list":
            do_connector_list()
        elif args.connector_command == "execute":
            do_connector_execute(args.name, args.tool, args.params)
    elif args.command == "provider":
        load_env_config(_profile)
        do_provider_list()
    elif args.command == "transform":
        do_transform(args.intent, args.provider, args.scope, args.profile)
    elif args.command == "workflow":
        if args.workflow_command == "init":
            do_workflow_init(args.name, args.profile, args.output)
        elif args.workflow_command == "run":
            do_workflow_run(args.file, args.intent)
    else:
        parser.print_help()

    # Only start server if --no-server not set and we have a valid command context
    cli_commands = {
        "status",
        "context",
        "ledger",
        "telemetry",
        "provider",
        "transform",
        "workflow",
    }
    if not args.no_server and args.command not in cli_commands:
        host = args.host
        port = args.port

        if port == 0:
            # Ledger mode: allocate a conflict-free port and advertise it so
            # connectors can discover the spine API without hard-coding it.
            from spine.portledger import PortLedger

            alloc = PortLedger().allocate("spine-api", 8000, 8000, 8020)
            port = alloc.actual
            print(f"PortLedger: spine-api allocated {port} (via {alloc.via})")

        print(f"Starting Transformation Spine on {host}:{port}")
        print(f"Profile: {_profile}")
        print(f"Access the API at http://{host}:{port}")
        print("Use 'spine status', 'spine context', 'spine transform <intent>', etc.")

        load_env_config(_profile)

        import uvicorn

        from spine.api import app as spine_app

        uvicorn.run(spine_app, host=host, port=port)


if __name__ == "__main__":
    main()
