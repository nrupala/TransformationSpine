"""TransformationSpine package.

Provider-neutral, context-lifecycle-driven orchestration spine. Models are
workers; the spine owns context, memory, decisions, governance, and provider
selection — so outcome convergence holds no matter which engine runs beneath.
"""

from .adapters import LlamaCppProvider, OllamaProvider, OpenAIProvider
from .connectors import (
    AzureDevOpsConnector,
    ConnectorResult,
    GitHubConnector,
    JiraConnector,
    MCPConnector,
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
    "CTSTRecord",
    "CTSTLedger",
    "LlamaCppProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "GitHubConnector",
    "AzureDevOpsConnector",
    "JiraConnector",
    "MCPConnector",
    "ToolDef",
    "ConnectorResult",
    "audit_permissions",
    "check_path_restriction",
    "enforce_safeguards",
    "get_project_root",
    "verify_write_protection",
]

__version__ = "0.1.0"
