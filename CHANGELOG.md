# Changelog

All notable changes to Transformation Spine are recorded here.

## [0.2.0] - 2026-10-09

### Added — Upgrade scope per BUILD_PLAN.md

#### Multi-backend adapters (Phase 1)
- `HuggingFaceProvider` adapter for HuggingFace Inference API + local transformers
- Provider factory (`spine.factory`) building adapters from profile-aware `Providers.yaml` specs
- `Providers.yaml` template with local/cloud/hybrid model groups
- Provider factory with profile-aware resolution (local/cloud/hybrid)

#### Expanded MCP/ACP connectors (Phase 2)
- `ServiceNowConnector` — incident, change, CMDB, service catalog
- `DatabricksConnector` — SQL endpoints, MLflow, workspace objects
- `ConfluenceConnector` — pages, spaces, attachments
- All six connectors exported from the package and covered by mock-transport tests (plugin auto-discovery was planned but is not implemented; connectors register by import)

#### Audit logs & telemetry (Phase 3)
- `ProviderResult.telemetry` dict for prompt/token/latency metrics
- `/telemetry` FastAPI endpoint — JSON aggregation of usage, latency, convergence
- `ContextStore` durable backing — facts in persisted scopes survive restarts (JSON, atomic write)
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
- Workflow module (`src/spine/workflow/`) — DAG execution engine (topological order, cycle detection, gate enforcement) with `spine workflow run`
- `docs/workflows.md` — workflow guide with examples

#### Prebuilt agent libraries (Phase 6)
- `code-review-agent` — wraps code-reviewer skill on transformation output
- `test-generator-agent` — produces pytest cases from function signatures
- `prompt-optimizer-agent` — auto-tunes prompts for better convergence
- `rag-pipeline-agent` — lexical retrieval (token-overlap scoring) over a supplied corpus; no vector backend is bundled
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
- `scripts/safeguard.sh` — runs the safeguard check/enforce CLI
- `enforce_safeguards` strips world-writable permissions across the project tree and reports only changes actually applied
- Safeguard posture (world-writable count) reported by `GET /api/v1/status`

### Audit remediation (2026-10-09) — fixes for the v0.2 claim audit

An independent audit struck the original "all phases complete, G0–G8 PASS"
claim; this release contains the remediation, each fix behavior-tested:

- **CTST tamper evidence (was inert):** hash chain is persisted per record,
  `verify_chain()` rewritten and exposed via `GET /api/v1/ledger/verify`
  and `spine ledger --verify`; tamper tests prove edited records fail.
- **Context persistence (was in-memory only):** durable store backing;
  promote/demote preserve provenance and creation time.
- **Convergence (was binary):** caller-side gate evaluation
  (`spine.gates`) computes the error signal deterministically; every
  transform cycle is ledgered with verdict, gates, and telemetry.
- **Token-efficiency engine:** route registry + token planner
  (`spine.tokenplan`), two-tier cache-stable context assembly
  (`spine.assembly`), session compaction checkpoints — ported from
  ENGINE-SPEC-v1 (the engine running live in MyMilo v0.35–v0.37).
- **Profiles (were decorative):** `spine.factory` builds providers per
  profile; CLI and API (SPINE_PROFILE) route through Routing.yaml.
- **Tool calls (were parsed, never run):** `spine.tools` registry +
  execution loop with `tools.yaml`; executions recorded in telemetry.
- **Workflow (was authoring-only):** execution engine with gates;
  `workflow init` also writes the documented `.mmd` file.
- **Agents (discovery/invoke were broken):** skills resolve from the
  repo root, doc-skills load via `instructions()`, `generate_tests`
  generates from the module's real AST, prompt-optimizer and lexical
  RAG agents implemented.
- **Release coherence:** package/API version 0.2.0 (was 0.1.0 in code),
  coverage ≥80% enforced in CI, `ruff format` checked in CI, license
  headers on all sources, local adapters ignore proxy env
  (`trust_env=False`), missing promised docs/files restored.

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
