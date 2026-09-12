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
import os
from pathlib import Path
from typing import Any

import httpx
import yaml

from spine import ContextStore
from spine.adapters import LlamaCppProvider, OpenAIProvider
from spine.provider import Provider

# Global spine instances (shared across CLI commands)
_spine_app = None
_spine_store: ContextStore | None = None
_spine_providers: dict[str, Any] = {}
_profile: str = "local"


def load_env_config(profile: str = "local") -> None:
    """Load configuration from Providers.yaml if present."""
    config_path = Path("Providers.yaml")
    if not config_path.exists():
        return

    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    global _spine_providers
    for provider_name, cfg in (data.get("providers") or {}).items():
        endpoint = cfg.get("endpoint", "")
        if endpoint:
            try:
                provider: Provider | None = None
                if provider_name == "openai" or provider_name == "anthropic":
                    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get(
                        "ANTHROPIC_API_KEY"
                    )
                    if api_key:
                        provider = OpenAIProvider(
                            api_key=api_key,
                            endpoint=endpoint,
                        )
                elif provider_name == "llama.cpp":
                    provider = LlamaCppProvider(endpoint=endpoint)

                if provider is not None:
                    _spine_providers[provider_name] = provider
                    print(f"Loaded provider: {provider_name}")
            except Exception as e:
                print(f"Could not load provider {provider_name}: {e}")


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


def do_transform(
    intent: str, provider: str, scope: str, profile: str
) -> None:
    """Execute the transform command."""
    _ = profile  # Profile for future use in provider selection

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


def do_ledger() -> None:
    """Execute the ledger command."""
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
    print(f"Created workflow '{name}' at {output_file}")
    print(f"Provider: {profile}")
    print("\nMermaid preview:")
    print(generate_mermaid(wf))


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
    subparsers.add_parser("ledger", help="Read CTST ledger entries")

    # spine telemetry
    subparsers.add_parser("telemetry", help="Show aggregated telemetry metrics")

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

    args = parser.parse_args()

    # Set global profile
    _profile = args.profile

    # Handle top-level commands
    if args.command == "status":
        do_status()
    elif args.command == "context":
        do_context()
    elif args.command == "ledger":
        do_ledger()
    elif args.command == "telemetry":
        do_telemetry()
    elif args.command == "provider":
        load_env_config(_profile)
        do_provider_list()
    elif args.command == "transform":
        do_transform(args.intent, args.provider, args.scope, args.profile)
    elif args.command == "workflow":
        if args.workflow_command == "init":
            do_workflow_init(args.name, args.profile, args.output)
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
