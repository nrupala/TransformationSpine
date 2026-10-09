<!-- Copyright 2026 Nrupal Akolkar -->
<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# Transformation Spine Build Plan v0.2.0

## Executive Summary

This build plan extends Transformation Spine from v0.1.0 (core provider neutrality) to v0.2.0 (enterprise-grade, multi-backend, observable system) while maintaining strict ASF gate compliance (G0-G8). All phases include verifiable exit conditions, QA/QC gates, and rollback paths per Apache Software Foundation methodology.

**Core Principle**: Enhancements are additive—existing code and interfaces remain unchanged. New capabilities extend, never replace.

## ASF Gate Compliance Overview

Every phase verifies:
- **G0**: Build system (`pyproject.toml` updated with new deps)
- **G1**: Tests (new unit/integration tests >=80% coverage)
- **G2**: Lint/typecheck (`ruff` clean, `mypy` strict)
- **G3**: License (Apache-2.0 maintained)
- **G4**: Contribution docs (updated as needed)
- **G5**: Reproducible install (clean-env verification)
- **G6**: Release process (CHANGELOG, semver tags)
- **G7**: Governance (ADR entries for significant changes)
- **G8**: CI/CD (workflow updated for new test matrix)

## Phase Structure

Each phase follows:
```
[PLAN] → [IMPLEMENT] → [TEST] → [QA/QC] → [GATE REVIEW] → [MERGE]
```

### Exit Criteria per Phase
1. All new tests pass (`pytest -q`)
2. Lint/typecheck clean (`ruff check && mypy src`)
3. ASF gates G0-G8 verified with evidence
4. No regressions in existing functionality
5. Documentation updated (README, API docs)
6. Rollback path tested (git revert + verification)

## Phase 1: Multi-Backend Adapters (HuggingFace + Skill-Level)

**Goal**: Add HuggingFace provider adapter + enable skill-level backend abstraction

### Files to Create/Modify
- `src/spine/adapters.py` → Add `HuggingFaceProvider` class
- `tests/test_adapters.py` → New adapter tests
- `Providers.yaml.example` → Add HF model entries
- `docs/adapters.md` → Provider adapter reference

### QA/QC Checks
- Provider protocol conformance (duck-typing test)
- HuggingFace adapter tested against mock HF API
- Fallback chain validation (HF → llama.cpp)
- Context propagation correctness

### Gate Evidence
- `python -m pytest tests/test_adapters.py -q` → PASS
- `python -m ruff check src/spine/adapters.py` → PASS
- `python -m mypy src/spine/adapters.py` → PASS

### Rollback Path
- Revert adapter additions
- Restore original `Providers.yaml.example`
- Verify existing tests still pass

## Phase 2: Expanded MCP/ACP Connectors + Plugin Framework

**Goal**: Add ServiceNow, Databricks, Confluence connectors + auto-discovery

### Files to Create/Modify
- `src/spine/connectors/` → New connector files:
  - `servicenow_connector.py`
  - `databricks_connector.py`
  - `confluence_connector.py`
- `src/spine/connectors/__init__.py` → Auto-discovery mechanism
- `tests/test_connectors/` → New connector test suites
- `docs/connectors.md` → Updated connector reference

### QA/QC Checks
- Each connector implements `MCPConnector` base
- Health check validates service reachability (mock)
- ToolDef schemas validate against service API
- Plugin discovery loads connectors without explicit import

### Gate Evidence
- Connector-specific test suites pass
- Plugin registry auto-loads 3+ new connectors
- Health checks return expected boolean values
- No lint/typecheck regressions

### Rollback Path
- Remove new connector files
- Revert `__init__.py` changes
- Verify original 3 connectors still function

## Phase 3: Audit Logs & Telemetry

**Goal**: Extend observability with Aider/Claude-style metrics

### Files to Create/Modify
- `src/spine/result.py` → Add `telemetry` dict to `ProviderResult`
- `src/spine/api.py` → Add `/telemetry` endpoint
- `src/spine/store.py` → Aggregate metrics (promote/demote counts)
- `tests/test_telemetry.py` → Metric aggregation tests
- `docs/telemetry.md` → Telemetry endpoint reference

### QA/QC Checks
- `ProviderResult` backward compatibility maintained
- `/telemetry` endpoint returns JSON metrics
- Aggregation accurate under concurrent load
- No performance regression (>5% latency increase)

### Gate Evidence
- `python -m pytest tests/test_telemetry.py -q` → PASS
- Telemetry endpoint returns 200 with correct schema
- Metrics match manual counts from CTST ledger
- Lint/typecheck clean on modified files

### Rollback Path
- Revert `ProviderResult.telemetry` addition
- Remove `/telemetry` endpoint
- Restore original `store.py` aggregation logic
- Verify telemetry-free operation

## Phase 4: Local/Cloud/Hybrid Profiles

**Goal**: Enable profile-based provider selection (local/cloud/hybrid)

### Files to Create/Modify
- `Providers.yaml` → Template with local/cloud/hybrid groups
- `Routing.yaml` → Template with profile-aware routing
- `src/spine/cli.py` → Add `--profile` flag to commands
- `src/spine/provider.py` → Profile-aware provider factory
- `docs/profiles.md` → Profile usage guide

### QA/QC Checks
- Profile selection resolves correct providers
- Fallback chains work per profile
- CLI help documents `--profile` options
- No hardcoded provider dependencies remain

### Gate Evidence
- `spine_cli transform --profile local ...` → Uses llama.cpp
- `spine_cli transform --profile cloud ...` → Uses OpenAI/Azure
- `spine_cli transform --profile hybrid ...` → Uses routing rules
- Profile validation rejects invalid names
- All existing CLI commands still work (default profile)

### Rollback Path
- Revert profile-related CLI changes
- Restore original provider factory
- Verify default behavior unchanged

## Phase 5: Graphical Workflow Authoring

**Goal**: Add Mermaid-based workflow visualization complementing scripts

### Files to Create/Modify
- `src/spine/workflow/` → New workflow module
- `src/spine/cli.py` → Add `workflow init` command
- `docs/workflows.md` → Mermaid workflow guide
- `examples/workflows/` → Sample Mermaid files
- `tests/test_workflow.py` → Workflow parsing/validation

### QA/QC Checks
- Mermaid syntax validation
- Workflow-to-execution mapping correctness
- CLI generates valid Mermaid from spec
- No interference with existing transform commands

### Gate Evidence
- `spine_cli workflow init --name "myflow"` → Creates valid `.mmd`
- Mermaid syntax check passes on generated files
- Workflow parser validates node/edge semantics
- Existing `transform` command unaffected

### Rollback Path
- Remove workflow module
- Revert CLI workflow command additions
- Verify no breakage to core functionality

## Phase 6: Prebuilt Agent Libraries

**Goal**: Register reusable skills in skill_registry

### Files to Create/Modify
- `skills/` → New agent skills:
  - `code-review-agent/`
  - `test-generator-agent/`
  - `prompt-optimizer-agent/`
- `skills/skill_registry/_index.md` → Updated registry entries
- `src/spine/agents/` → Agent invocation adapters
- `tests/test_agents/` → Agent skill tests

### QA/QC Checks
- Skills follow skill_registry format (YAML header + location)
- Agent skills invoke without spine modification
- Code-review agent runs on transformation output
- Test generator produces syntactically valid pytest

### Gate Evidence
- New entries in `skill_registry/_index.md` with verified status
- Agent skills load and execute in test harness
- Generated code passes basic syntax checks
- No spine core modifications required

### Rollback Path
- Remove skill directories
- Revert skill_registry index changes
- Verify existing skills still load

## Phase 7: Enterprise Integrations Roadmap

**Goal**: Document prioritized enterprise connector roadmap

### Files to Create/Modify
- `docs/enterprise_roadmap.md` → Prioritization matrix
- `ROADMAP.md` → Top-level product roadmap
- `CONTRIBUTING.md` → Enterprise contribution guidelines

### QA/QC Checks
- Roadmap aligns with stated priorities (ServiceNow, Databricks first)
- Contribution guidelines clarify enterprise processes
- Dependencies and timelines clearly documented

### Gate Evidence
- Roadmap reviewed and approved via ADR process
- Contribution guidelines complete and actionable
- No implementation yet—documentation-only phase

### Rollback Path
- Simply remove/update documentation files
- No code impact

## Phase 8: Tool-Call Abstraction

**Goal**: Add OpenAI-function-call style tool use to ProviderResult

### Files to Create/Modify
- `src/spine/result.py` → Add `tool_calls` optional field to `ProviderResult`
- `src/spine/provider.py` → Update `Provider` protocol for tool use
- `src/spine/adapters.py` → Update adapters to handle tool responses
- `tests/test_tool_calls.py` → Tool call/response tests
- `docs/tool_calls.md` → Tool abstraction guide

### QA/QC Checks
- Backward compatibility (tool_calls=None default)
- Adapters correctly parse tool-use responses
- Spine router handles tool-call → tool-execute cycles
- JSON Schema validation for tool parameters

### Gate Evidence
- Tool call tests pass with mock adapters
- Provider protocol maintains LSP compliance
- Round-trip: tool request → execution → result works
- No breaking changes to existing complete() usage

### Rollback Path
- Revert `ProviderResult.tool_calls` addition
- Restore original provider protocol
- Verify existing adapter contracts unchanged

## Phase 9: OS-Level Safeguarding + Finalization

**Goal**: Implement file-system safeguards per §10 (no Docker)

### Files to Create/Modify
- `scripts/safeguard.sh` → Sets restrictive file permissions
- `docs/safeguarding.md` → OS-level isolation guide
- `.gitignore` → Add safeguard artifacts
- `backup-before-write` skill integration verification

### QA/QC Checks
- Spine process runs with least-privilege file access
- Write attempts outside project directory fail
- Read access to project works normally
- Safeguard script idempotent and safe

### Gate Evidence
- File permission audits show correct restrictions
- Write-protected directories reject spine writes
- Project directory allows necessary operations
- No privilege escalation paths identified

### Rollback Path
- Revert safeguard permission changes
- Verify project still functional with standard perms
- Document as optional hardening step

## Overall Timeline & Milestones

| Phase | Duration | Exit Gate | Dependencies |
|-------|----------|-----------|--------------|
| 1 | 1-2 days | G0-G8 verified | None |
| 2 | 2-3 days | G0-G8 verified | Phase 1 |
| 3 | 1-2 days | G0-G8 verified | Phase 1,2 |
| 4 | 1 day | G0-G8 verified | Phase 1 |
| 5 | 1 day | G0-G8 verified | None |
| 6 | 1 day | G0-G8 verified | None |
| 7 | 0.5 day | Documentation complete | None |
| 8 | 1-2 days | G0-G8 verified | Phase 1 |
| 9 | 0.5 day | Safeguard verified | All phases |

**Total Estimated**: 10-14 days of development effort

## Quality Assurance & Risk Mitigation

### Verification Checkpoints
1. **Daily**: `pytest -q` + `ruff check` + `mypy src`
2. **Pre-merge**: Full test suite + ASF gate verification
3. **Post-merge**: Staging environment validation
4. **Pre-release**: Release candidate testing

### Risk Categories & Mitigation
- **Interface breakage**: Mitigated by protocol testing + backward compatibility
- **Performance regression**: Mitigated by benchmarking critical paths
- **Security issues**: Mitigated by least-privilege design + safeguards
- **Documentation drift**: Mitigated by doc updates as part of each phase
- **Test flakiness**: Mitigated by deterministic mocks + seed control

### Rollback Strategy
- Each phase creates a dedicated git branch
- Failed phases can be abandoned without affecting main
- Emergency rollback: `git reset --hard <pre-phase-tag>`
- Data migration: CTST ledger format versioned for forward compatibility

## Approval Checklist

Before implementation begins, verify:
- [ ] All ASF gates G0-G8 currently PASS (verified in GATES.md)
- [ ] No pending exemptions in ASFQC/GATES.md
- [ ] Development environment matches standing rules (§2, §10, §17)
- [ ] Backup of current working state taken
- [ ] Team agreement on phase prioritization

## Success Metrics

Upon completion of v0.2.0:
- ✅ Provider neutrality extends to HuggingFace + skill-level adapters
- ✅ MCP/ACP connectors cover 6+ industry services (GitHub, ADO, Jira, ServiceNow, Databricks, Confluence)
- ✅ Telemetry provides Aider/Claude-style observability
- ✅ Local/cloud/hybrid profiles enable flexible deployment
- ✅ Workflow visualization complements scripting without replacement
- ✅ Prebuilt agent libraries accelerate common tasks
- ✅ Enterprise integration roadmap guides future development
- ✅ Tool-call abstraction enables interoperability with LangGraph/Orca
- ✅ OS-level safeguarding achievable without Docker per §10
- ✅ All ASF gates G0-G8 PASS with recorded evidence
- ✅ Zero breaking changes to v0.1.0 public interfaces
- ✅ Test coverage maintains or improves from v0.1.0 baseline

---
*This build plan adheres to Apache Software Foundation methodology: every phase is gated, verified, and rollback-capable. Enterprise readiness is inherent in ASF compliance—scalable, secure, and professionally maintained.*