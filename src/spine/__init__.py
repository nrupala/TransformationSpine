# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: AGPL-3.0-or-later
"""TransformationSpine package.

Provider-neutral, context-lifecycle-driven orchestration spine. Models are
workers; the spine owns context, memory, decisions, governance, and provider
selection — so outcome convergence holds no matter which engine runs beneath.
"""

from .adapters import (
    HuggingFaceLocalProvider,
    HuggingFaceProvider,
    LlamaCppProvider,
    OllamaProvider,
    OpenAIProvider,
)
from .assembly import Assembly, assemble_context
from .connectors import (
    AzureDevOpsConnector,
    ConfluenceConnector,
    ConnectorResult,
    DatabricksConnector,
    GitHubConnector,
    JiraConnector,
    MCPConnector,
    ServiceNowConnector,
    ToolDef,
)
from .context import (
    SCOPE_POLICIES,
    ContextFact,
    ContextScope,
    ScopePolicy,
    declare,
)
from .ctst import CTSTLedger, CTSTRecord
from .discovery import ConnectorRegistry, DiscoveryResult, discover_connectors
from .factory import (
    build_provider_map,
    canonical_provider,
    parse_provider_specs,
    select_for_task,
)
from .gates import GateCheck, GateReport, evaluate_result
from .provider import ModelSpec, Provider, RouterRule
from .result import ProviderResult
from .safeguard import (
    audit_permissions,
    check_path_restriction,
    enforce_safeguards,
    get_project_root,
    verify_write_protection,
)
from .store import ContextStore, ScopeViolationError, snapshot_for_prompt
from .tokenplan import (
    ContextOverflowError,
    RouteSpec,
    estimate_tokens,
    plan_max_tokens,
    route_spec,
)
from .tools import ToolRegistry, run_tool_loop

__all__ = [
    "ContextFact",
    "ContextScope",
    "ScopePolicy",
    "SCOPE_POLICIES",
    "declare",
    "ModelSpec",
    "Provider",
    "RouterRule",
    "ProviderResult",
    "ContextStore",
    "ScopeViolationError",
    "snapshot_for_prompt",
    "ToolRegistry",
    "run_tool_loop",
    "CTSTRecord",
    "CTSTLedger",
    "build_provider_map",
    "ConnectorRegistry",
    "DiscoveryResult",
    "discover_connectors",
    "canonical_provider",
    "parse_provider_specs",
    "select_for_task",
    "GateCheck",
    "GateReport",
    "evaluate_result",
    "Assembly",
    "assemble_context",
    "RouteSpec",
    "route_spec",
    "plan_max_tokens",
    "estimate_tokens",
    "ContextOverflowError",
    "LlamaCppProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "HuggingFaceProvider",
    "HuggingFaceLocalProvider",
    "GitHubConnector",
    "AzureDevOpsConnector",
    "JiraConnector",
    "ServiceNowConnector",
    "DatabricksConnector",
    "ConfluenceConnector",
    "MCPConnector",
    "ToolDef",
    "ConnectorResult",
    "audit_permissions",
    "check_path_restriction",
    "enforce_safeguards",
    "get_project_root",
    "verify_write_protection",
]

__version__ = "0.3.0"
