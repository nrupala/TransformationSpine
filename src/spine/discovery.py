# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Connector plugin auto-discovery.

The v0.2 CHANGELOG promised plugin-based connector discovery; until
this module it did not exist — connectors registered only by import in
``spine/__init__``. Discovery now works three ways, in one registry:

1. **Built-ins** — the six connectors shipped in ``spine.connectors``.
2. **Entry points** — any installed distribution may advertise
   connectors under the ``spine.connectors`` entry-point group; the
   entry point must resolve to an ``MCPConnector`` subclass.
3. **Directory plugins** — directories listed in the
   ``SPINE_CONNECTOR_PATH`` env var (``os.pathsep``-separated) plus a
   local ``connectors/`` directory are scanned for ``.py`` modules;
   every ``MCPConnector`` subclass a module defines is registered.

Discovery never raises: a broken plugin is recorded in
``DiscoveryResult.errors`` and discovery continues — one bad plugin
must not take down the spine. Duplicate names keep the first
registration (built-ins win over entry points win over directories)
and are recorded as skipped.

Instantiation is config-aware without being connector-aware: for each
``__init__`` parameter, ``ConnectorRegistry`` looks for an env var
``SPINE_CONNECTOR_<NAME>_<PARAM>`` (uppercased) and passes it when
set, so operators configure any connector — built-in or plugin — the
same way, e.g. ``SPINE_CONNECTOR_GITHUB_TOKEN``.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import inspect
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .connectors import (
    AzureDevOpsConnector,
    ConfluenceConnector,
    DatabricksConnector,
    GitHubConnector,
    JiraConnector,
    MCPConnector,
    ServiceNowConnector,
)

BUILTIN_CONNECTORS: dict[str, type[MCPConnector]] = {
    "github": GitHubConnector,
    "azuredevops": AzureDevOpsConnector,
    "jira": JiraConnector,
    "servicenow": ServiceNowConnector,
    "databricks": DatabricksConnector,
    "confluence": ConfluenceConnector,
}

ENTRY_POINT_GROUP = "spine.connectors"


@dataclass
class DiscoveryResult:
    """What discovery found: connector classes by name, plus the record
    of anything skipped or broken (never silently swallowed)."""

    connectors: dict[str, type[MCPConnector]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)


def _register(
    result: DiscoveryResult,
    cls: type[MCPConnector],
    source: str,
) -> None:
    name = getattr(cls, "name", "") or cls.__name__.lower()
    if name in result.connectors:
        result.skipped.append(f"{name} from {source} (already registered)")
        return
    result.connectors[name] = cls
    result.sources[name] = source


def _classes_from_module(module: Any) -> list[type[MCPConnector]]:
    found: list[type[MCPConnector]] = []
    for _attr, obj in sorted(vars(module).items()):
        if (
            inspect.isclass(obj)
            and issubclass(obj, MCPConnector)
            and obj is not MCPConnector
            and obj.__module__ == module.__name__
        ):
            found.append(obj)
    return found


def discover_connectors(
    *,
    search_paths: list[str | Path] | None = None,
    include_entry_points: bool = True,
    include_builtins: bool = True,
) -> DiscoveryResult:
    """Run all discovery sources and return the combined registry."""
    result = DiscoveryResult()

    if include_builtins:
        for cls in BUILTIN_CONNECTORS.values():
            _register(result, cls, "builtin")

    if include_entry_points:
        try:
            eps: Any = importlib.metadata.entry_points()
            if hasattr(eps, "select"):
                selected = eps.select(group=ENTRY_POINT_GROUP)
            else:  # very old Python: entry_points() returned a dict
                selected = eps.get(ENTRY_POINT_GROUP, [])
            for ep in selected:
                try:
                    obj = ep.load()
                    if inspect.isclass(obj) and issubclass(obj, MCPConnector):
                        _register(result, obj, f"entrypoint:{ep.name}")
                    else:
                        result.errors.append(
                            f"entry point {ep.name}: not an MCPConnector subclass"
                        )
                except Exception as e:  # a broken plugin must not stop discovery
                    result.errors.append(
                        f"entry point {ep.name}: {type(e).__name__}: {e}"
                    )
        except Exception as e:
            result.errors.append(f"entry point scan: {type(e).__name__}: {e}")

    paths: list[Path] = [Path(p) for p in search_paths or []]
    env_paths = os.environ.get("SPINE_CONNECTOR_PATH", "")
    if env_paths:
        paths.extend(Path(p) for p in env_paths.split(os.pathsep) if p)
    local_dir = Path.cwd() / "connectors"
    if local_dir.is_dir():
        paths.append(local_dir)

    for directory in paths:
        if not directory.is_dir():
            result.errors.append(f"plugin path not a directory: {directory}")
            continue
        for file in sorted(directory.glob("*.py")):
            if file.name.startswith("_"):
                continue
            module_name = f"spine_plugin_{directory.name}_{file.stem}"
            try:
                spec = importlib.util.spec_from_file_location(module_name, file)
                if spec is None or spec.loader is None:
                    result.errors.append(f"{file}: cannot load module spec")
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                for cls in _classes_from_module(module):
                    _register(result, cls, f"path:{file}")
            except Exception as e:  # keep discovering past broken plugins
                result.errors.append(f"{file}: {type(e).__name__}: {e}")

    return result


def _env_config(name: str, cls: type[MCPConnector]) -> dict[str, Any]:
    """Build constructor kwargs for a connector from env vars."""
    kwargs: dict[str, Any] = {}
    try:
        params = inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):
        return kwargs
    prefix = f"SPINE_CONNECTOR_{name.upper()}_"
    for param in params:
        if param in ("self", "args", "kwargs"):
            continue
        value = os.environ.get(prefix + param.upper())
        if value is not None:
            kwargs[param] = value
    return kwargs


class ConnectorRegistry:
    """Instantiated connectors, built from a DiscoveryResult."""

    def __init__(self, discovery: DiscoveryResult) -> None:
        self.discovery = discovery
        self._instances: dict[str, MCPConnector] = {}
        self.instantiation_errors: list[str] = []
        for name, cls in discovery.connectors.items():
            try:
                self._instances[name] = cls(**_env_config(name, cls))
            except Exception as e:
                self.instantiation_errors.append(f"{name}: {type(e).__name__}: {e}")

    @classmethod
    def discover(cls, **kwargs: Any) -> ConnectorRegistry:
        return cls(discover_connectors(**kwargs))

    def names(self) -> list[str]:
        return sorted(self._instances)

    def get(self, name: str) -> MCPConnector | None:
        return self._instances.get(name)

    def describe(self) -> list[dict[str, Any]]:
        """Name, source, capabilities, and health for every connector."""
        out: list[dict[str, Any]] = []
        for name in self.names():
            conn = self._instances[name]
            try:
                caps = [c.name for c in conn.declare_capabilities()]
            except Exception:
                caps = []
            out.append(
                {
                    "name": name,
                    "source": self.discovery.sources.get(name, ""),
                    "capabilities": caps,
                }
            )
        return out
