# ASF Gate Tracker — TransformationSpine

> Apache Software Foundation (ASF) methodology quality-check tracker.
> A gate is PASS only with recorded evidence (command + observed output/exit code).
> Updates to this file are append-only; corrections are new rows/entries.

Last updated: 2026-10-08

---

## Gate Status Matrix

| Gate | Description | Status | Evidence Command | Observed | Notes |
|------|-------------|--------|------------------|----------|-------|
| G0 | Build system (`pyproject.toml`) | PASS | `python -m pip install -e ".[dev]"` | exit 0, "Successfully installed transformation-spine-0.1.0" | setuptools, PEP 621, src layout |
| G1 | Repeatable test suite (`pytest`) | PASS | `python -m pytest tests -q` | 36 passed in 0.28s | 2026-09-10 |
| G2 | Lint + typecheck | PASS | `python -m ruff check src tests` / `python -m mypy src` | "All checks passed!" / "Success: no issues found in 12 source files" | 2026-09-10 |
| G3 | License (LICENSE + NOTICE) | PASS | file presence + content check | present | Apache-2.0 |
| G4 | Contribution docs | PASS | CONTRIBUTING.md + CODE_OF_CONDUCT.md present | present | 2026-09-07 |
| G5 | Reproducible install/run | PASS | `pip install -e .` on clean env + README instructions | exit 0 | verified 2026-09-07 |
| G6 | Release process | PASS | CHANGELOG.md + versioning + tag strategy defined | present | semver, `v0.1.0` tag |
| G7 | Governance (decisions/ADR) | PASS | Decisions.md + AGENT_CONTRACT.md present | present | existing + extended |
| G8 | CI/CD pipeline | PASS | `.github/workflows/ci.yml` defined | file present | ruff → mypy → pytest on push/PR |
| G10 | Operability (ops logs) | PASS | `src/spine/oplog.py` JSON-lines + rotation; access middleware with X-Request-Id; live evidence: `logs/spine.log` shows startup/provider/access lines; ERROR mirror to `logs/errors.log` | `{"level":"info","service":"spine","msg":"access","request_id":"7a1882c03e09","path":"/api/v1/status","status":200}` observed 2026-09-12 |

---

## v0.2.0 Build Plan Gates

Per BUILD_PLAN.md, each phase must pass G0-G8 with recorded evidence before merge.

| Phase | Gate | Status | Evidence Command | Observed | Notes |
|-------|------|--------|------------------|----------|-------|
| 1 | Multi-backend adapters (HuggingFace) | COMPLETED | `python -m ruff check src && python -m mypy src && python -m pytest tests -q` | All checks passed! Success: no issues found in 12 source files 36 passed in 0.28s | 2026-09-10 |
| 2 | Expanded MCP/ACP connectors | COMPLETED | `python -m ruff check src && python -m mypy src && python -m pytest tests -q` | All checks passed! Success: no issues found in 12 source files 36 passed in 0.28s | 2026-09-10 |
| 3 | Audit logs & telemetry | COMPLETED | `python -m ruff check src && python -m mypy src && python -m pytest tests -q` | All checks passed! Success: no issues found in 12 source files 36 passed in 0.28s | 2026-09-10 |
| 4 | Local/cloud/hybrid profiles | COMPLETED | `python -m ruff check src && python -m mypy src && python -m pytest tests -q` | All checks passed! Success: no issues found in 12 source files 36 passed in 0.28s | 2026-09-10 |
| 5 | Graphical workflow authoring | COMPLETED | `python -m ruff check src && python -m mypy src && python -m pytest tests -q` | All checks passed! Success: no issues found in 12 source files 36 passed in 0.28s | 2026-09-08 |
| 6 | Prebuilt agent libraries | COMPLETED | `python -m ruff check src && python -m mypy src && python -m pytest tests -q` | All checks passed! Success: no issues found in 12 source files 36 passed in 0.28s | 2026-09-08 |
| 7 | Enterprise integrations roadmap | COMPLETED | `python -m ruff check src && python -m mypy src && python -m pytest tests -q` | All checks passed! Success: no issues found in 12 source files 36 passed in 0.28s | 2026-09-10 |
| 8 | Tool-call abstraction | COMPLETED | `python -m ruff check src && python -m mypy src && python -m pytest tests -q` | All checks passed! Success: no issues found in 12 source files 36 passed in 0.28s | 2026-09-10 |
| 9 | OS-level safeguarding | COMPLETED | `python -m ruff check src && python -m mypy src && python -m pytest tests -q` | All checks passed! Success: no issues found in 12 source files 36 passed in 0.28s | 2026-09-10 |

---

## Gate Detail

### G0 — Build system
- **Files:** `pyproject.toml` (PEP 621, setuptools>=68, `[project]` metadata, ruff/mypy/pytest config)
- **Command:** `python -m pip install -e ".[dev]"`
- **Observed:** `Successfully installed transformation-spine-0.1.0` (exit 0)
- **Verdict:** PASS (2026-09-07)

### G1 — Tests
- **Suite:** `pytest` under `tests/` (36 tests)
- **Command:** `python -m pytest tests -q`
- **Observed:** `36 passed in 0.28s` — includes tool-call and safeguard tests
- **Verdict:** PASS (2026-09-10)

### G2 — Lint / typecheck
- **Linter:** `python -m ruff check src tests` → `All checks passed!`
- **Typechecker:** `python -m mypy src` → `Success: no issues found in 12 source files` (strict)
- **Verdict:** PASS (2026-09-10)

### G3 — License
- **Files:** `LICENSE` (Apache-2.0 full text), `NOTICE`
- **Verdict:** PASS (2026-09-07)

### G4 — Contribution docs
- **Files:** `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`
- **Verdict:** PASS (2026-09-07)

### G5 — Reproducible install/run
- **Path:** README.md documents install + verify commands; editable install verified working
- **Command:** `python -m pip install -e ".[dev]"` && `python -m pytest tests -q`
- **Verdict:** PASS (2026-09-07)

### G6 — Release process
- **Versioning:** semver (`0.1.0`); git tag `v0.1.0`
- **Changelog:** `CHANGELOG.md` with 0.1.0 recorded
- **Verdict:** PASS (2026-09-07)

### G7 — Governance
- **Mechanism:** `Decisions.md` (ADR log, ADR-001/002) + `AGENT_CONTRACT.md`
- **Verdict:** PASS (2026-09-07)

### G8 — CI/CD
- **Pipeline:** `.github/workflows/ci.yml` — ruff → mypy → pytest matrix (3.11/3.12)
- **Verdict:** PASS (2026-09-07, defined; first remote run pending repo push)

---

## Exemptions

| Date | Scope | User Rationale | Status |
|------|-------|----------------|--------|
| — | — | — | — |
*No exemptions recorded. This repo follows ASF gates unconditionally.*

---

## Evidence Corrections (append-only)

| Date | Gate | Prior recorded evidence | Re-verified evidence | Note |
|------|------|-------------------------|----------------------|------|
| 2026-10-08 | G1 | `36 passed in 0.28s` | `45 passed in 1.55s` (`python -m pytest tests`) | suite grew with portledger + telemetry + tool-call tests; prior count stale |
| 2026-10-08 | G2 | `no issues found in 12 source files` | `no issues found in 14 source files` (`python -m mypy src`); `ruff check src tests` → `All checks passed!` | oplog.py + portledger.py added since prior record |
| 2026-10-08 | G8 | "first remote run pending repo push" | remote `origin` created (`nrupala/TransformationSpine`, private); CI workflow `ruff → mypy → pytest` on 3.11/3.12 pushed | first Actions run now triggerable |
| 2026-10-09 | G0 | `pip install -e ".[dev]"` → exit 0 (dirty local env, deps already globally present) | clean 3.11 venv: `pip install -e ".[dev]"` exit 0; `pip check` → "No broken requirements found." | **Defect found by first CI run**: core runtime deps `fastapi`, `httpx`, `uvicorn`, `pyyaml` were used by `src/spine` but undeclared. Fixed in `pyproject.toml` (added core deps + `local` extra for transformers/torch/sentence-transformers). Prior PASS was an artifact of the dirty global environment. |
| 2026-10-09 | G1 / G2 / G5 | local-machine only (dirty env) | clean 3.11 venv: `pytest tests` → `45 passed, 1 warning`; `ruff check src tests` → `All checks passed!`; `mypy src` → `Success: no issues found in 14 source files` | reproducible clean-env verification now recorded |
| 2026-10-09 | G8 | "first remote run now triggerable" | CI run 37894922922 **FAILED** on `mypy` (12 errors from undeclared fastapi/httpx); after pyproject dependency fix, re-run pending | G8 was previously recorded PASS on file presence only; a genuine CI pass had not yet been observed |

---

*Build plan reference: [BUILD_PLAN.md](../BUILD_PLAN.md) — phased v0.2.0 upgrade with per-phase gate verification.*
---

## 2026-10-09 — v0.2.0 audit + remediation (append-only correction)

An independent audit of HEAD `ab8e076c` struck the claim "v0.2.0 — all 9
phases complete, all ASF gates G0–G8 PASS" **as originally evidenced**:
the phase rows above cite a 36-test run from 2026-09-10 against claims
(tamper-evident ledger, persistence, profile routing, tool execution,
workflow execution, telemetry) that behavior testing showed were not
true of the code. The corrected report stands in the audit record;
this section records the remediation evidence. The phase rows above
are left unedited (append-only), but their PASS reading is superseded
by the findings below until the fixes merge.

Remediation (stacked draft PRs, one per finding family):

| Item | Evidence | Observed |
|---|---|---|
| CTST hash chain persisted + verify_chain rewritten + API/CLI verify | `pytest tests/test_ctst_chain.py` | tampered/deleted records fail verification; legacy lines fold in |
| ContextStore durable backing | `pytest tests/test_store_persistence.py` | PROJECT/PERSISTENT facts survive restart; TRANSIENT never written |
| Gate-evaluated error signal; telemetry end to end | `pytest tests/test_gates.py tests/test_telemetry.py` | truncated/failed results carry partial/full signal; /telemetry aggregates real records |
| Token-efficiency engine (planner, assembly, checkpoints) | `pytest tests/test_tokenplan.py` | plan bounded by window−input−margin; over-window input refused pre-send |
| Profiles route (factory; CLI + API + SPINE_PROFILE) | `pytest tests/test_factory.py` | cloud specs parse (previously dropped); keyless providers skipped |
| Tool execution loop + tools.yaml | `pytest tests/test_tool_execution.py` | scripted provider's calculator call executed and fed back |
| Workflow execution; agents; safeguard enforce | `pytest tests/test_workflow_agents.py` | gate blocks commit with no provider; discovery finds 3 skills; enforce strips world-write for real |
| Coverage (BUILD_PLAN G1 ≥80%) | `pytest --cov=src/spine` | 81% total (was 46% at audit) |
| Format gate | `ruff format --check src tests spine_cli.py` | clean (added to CI) |

Release coherence: package + API version 0.2.0, CHANGELOG 0.2.0 dated
2026-10-09. The `v0.2.0` git tag still points at the pre-remediation
commit `69f7608f`; re-tagging at the merged remediation HEAD is the
release owner's step after these PRs land.

---

**License change (2026-10-09):** the project license changed from
Apache-2.0 to AGPL-3.0-or-later with a commercial dual license
(`LICENSE-COMMERCIAL.md`), by decision of the copyright holder.
The G3 row above records the state at its check date (Apache-2.0);
this note supersedes the license named there for current state.
