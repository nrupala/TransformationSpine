# Changelog

All notable changes to Transformation Spine are recorded here.

## [0.2.0] - UNRELEASED (planned)

### Added — Upgrade scope per BUILD_PLAN.md

#### Multi-backend adapters (Phase 1)
- `HuggingFaceProvider` adapter for HuggingFace Inference API + local transformers
- Skill-level backend abstraction — adapters at the "skill" level, not just primitive inference calls
- `Providers.yaml` template with local/cloud/hybrid model groups
- Provider factory with profile-aware resolution (local/cloud/hybrid)

#### Expanded MCP/ACP connectors (Phase 2)
- `ServiceNowConnector` — incident, change, CMDB, service catalog
- `DatabricksConnector` — SQL endpoints, MLflow, workspace objects
- `ConfluenceConnector` — pages, spaces, attachments
- Plugin-based connector discovery (auto-load connectors from connectors/ directory)
- `MCPConnector` base class extended with `service_name` + `service_type` metadata

#### Audit logs & telemetry (Phase 3)
- `ProviderResult.telemetry` dict for prompt/token/latency metrics
- `/telemetry` FastAPI endpoint — JSON aggregation of usage, latency, convergence
- `ContextStore` metrics — promote/demote counts, scope transitions
- CTST ledger already append-only (audit trail); telemetry extends with analytics

#### Local/cloud/hybrid profiles (Phase 4)
- `spine_cli transform --profile local|cloud|hybrid`
- Profile selection via env var `SPINE_PROFILE` or CLI flag
- Fallback chain resolution per profile
- CLI help documents profile options

#### Graphical workflow authoring (Phase 5)
- `spine_cli workflow init --name "myflow"` — generates Mermaid `.mmd` file
- Workflow parser validates node/edge semantics
- Mermaid syntax validation
- Workflow module (`src/spine/workflow/`) — DAG execution engine
- `docs/workflows.md` — workflow guide with examples

#### Prebuilt agent libraries (Phase 6)
- `code-review-agent` — wraps code-reviewer skill on transformation output
- `test-generator-agent` — produces pytest cases from function signatures
- `prompt-optimizer-agent` — auto-tunes prompts for better convergence
- `rag-pipeline-agent` — vector-retrieve from Qdrant, feed into complete()
- Skills registered in `skill_registry/_index.md` with verified status

#### Enterprise integrations roadmap (Phase 7)
- `docs/enterprise_roadmap.md` — prioritization matrix (ServiceNow, Databricks first)
- `ROADMAP.md` — top-level product roadmap
- `CONTRIBUTING.md` updated with enterprise contribution guidelines

#### Tool-call abstraction (Phase 8)
- `ProviderResult.tool_calls` optional field — OpenAI function-call format
- Provider protocol extended for tool use (backward compatible)
- Adapters handle tool-call → tool-execute cycles
- `tools.yaml` — centralized tool registry with JSON Schema
- Interoperability with LangGraph/Orca-style function calling

#### OS-level safeguarding (Phase 9)
- `scripts/safeguard.sh` — sets least-privilege file permissions
- Read-only source directories, write-restricted paths
- Backup-before-write integration verification
- WSL/bwrap sandboxing without Docker per standing rule §10

### Changed
- All phases maintain ASF gate compliance (G0-G8) with recorded evidence
- Zero breaking changes to v0.1.0 public interfaces
- Build plan follows phased approach with verified exit conditions per phase

### Fixed
- Declared previously missing core runtime dependencies in `pyproject.toml`:
  `fastapi`, `httpx`, `uvicorn`, `pyyaml`. They were imported by `src/spine`
  but only present via the developer's global environment, so a clean install
  failed mypy in CI. Added a `local` optional extra for the heavyweight
  HuggingFace stack (`transformers`, `torch`, `sentence-transformers`).
  Verified by a clean Python 3.11 venv (install + ruff + mypy + 45 tests PASS).

## [0.1.0] - 2026-09-07

### Added

- Context lifecycle scoping model (`src/spine/context.py`):
  `ContextScope` (TRANSIENT / SESSION / PROJECT / PERSISTENT), `ScopePolicy`
  table, `ContextFact` with provenance and TTL expiry.
- Context store (`src/spine/store.py`): promote / demote / consolidate-session
  / expire, scope visibility (`visible_to`), deterministic prompt snapshot.
- Provider abstraction (`src/spine/provider.py`): `Provider` protocol,
  `ModelSpec` / `RouterRule` typed config parsing from the repo YAML shapes.
- Result + convergence model (`src/spine/result.py`): `ProviderResult` with
  `error_signal` (0.0 = converged).
- Test suite (17 tests): scope ordering, promotion/demotion legality, session
  consolidation, expiry pruning, deterministic snapshots, and the cross-engine
  convergence test (small llama.cpp-style vs large Codex-style fake providers
  converge to the same committed artifact with provenance preserved).
- Build system: `pyproject.toml` (setuptools, PEP 621, ruff + mypy + pytest
  config).
- ASF Gate tracker `ASFQC/GATES.md`; LICENSE (Apache-2.0), NOTICE,
  CONTRIBUTING.md, CODE_OF_CONDUCT.md, README.md.
- Git repository initialized.

## Versioning

Semantic Versioning (semver). Tagged releases: `v0.1.0`, `v0.2.0`, etc.
