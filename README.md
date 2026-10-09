# Transformation Spine

Provider-neutral transformation platform. Models are workers; the spine owns
context, memory, decisions, governance, and provider selection — so outcome
convergence holds no matter which engine runs beneath (llama.cpp, Codex,
openenry, Claude Code, any OpenAI-compatible endpoint).

## Core Idea

**Context is contextual to its usage.** Like variables in a compiled language,
the spine assigns every piece of context a lifetime:

| Scope | Analogy | Durability | Persisted |
|-------|---------|-----------|-----------|
| `TRANSIENT` | temporaries | one call | no |
| `SESSION` | stack frame | one task/session | while open |
| `PROJECT` | module state | project lifecycle | yes |
| `PERSISTENT` | globals in code | forever | yes |

The spine assembles the *minimum sufficient* in-scope context for each prompt,
promotes proven facts up a scope, demotes superseded decisions down, and
retires the ephemeral — without the model ever owning memory.

## Outcome Convergence

From the OCS projects: every transformation is
a gated cycle. The spine computes an error signal per provider result; a
result converges when the gap to the committed artifact is zero. This is what
makes a 8B llama.cpp model and a 70B Codex model converge to the same outcome —
swapping an engine is a configuration change, not a data loss event.

## Package

```
src/spine/
  context.py    ContextScope enum, ScopePolicy table, ContextFact
  store.py      ContextStore (promote/demote/consolidate/expire)
  provider.py   Provider protocol, ModelSpec, RouterRule
  result.py     ProviderResult (error_signal, convergence)
  adapters.py   LlamaCppProvider, OllamaProvider, OpenAIProvider
  connectors.py MCP/ACP connectors (GitHub, Azure DevOps, Jira)
  ctst.py       CTSTLedger (append-only JSONL with hash chain)
  api.py        FastAPI spine application
tests/
  test_scope.py, test_store.py, test_convergence.py
```

## Architecture

See [docs/spine-architecture.mmd](docs/spine-architecture.mmd) for the full architecture diagram.

## Build Plan

See [BUILD_PLAN.md](BUILD_PLAN.md) for the phased v0.2.0 upgrade plan covering:
- Multi-backend adapters (HuggingFace, skill-level)
- Expanded MCP/ACP connectors (ServiceNow, Databricks, Confluence)
- Audit logs & telemetry
- Local/cloud/hybrid profiles
- Graphical workflow authoring
- Prebuilt agent libraries
- Enterprise integrations roadmap
- Tool-call abstraction
- OS-level safeguarding

All phases maintain ASF gate compliance (G0-G8) with verified evidence.

## Install

```bash
python -m pip install -e ".[dev]"
```

## Test / verify

```bash
python -m pytest tests
python -m ruff check src tests
python -m mypy src
```

## Status

v0.1.0 — Core spine with provider abstraction, context lifecycle, CTST ledger,
and MCP/ACP connectors. All 8 ASF gates PASS with recorded evidence.

v0.2.0 — Completed per BUILD_PLAN.md: all 9 phases verified with pytest/ruff/mypy PASS,
36 tests passing, enterprise roadmap documented, tool-call abstraction implemented,
OS-level safeguarding in place. All ASF gates G0-G8 PASS with recorded evidence.
<!-- coffee-support -->
## Support
<a href="https://buymeacoffee.com/nrupalakolt" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy me a coffee" style="height:40px;" /></a>

## License

TransformationSpine is dual-licensed by its copyright holder,
Nrupal Akolkar:

- **Open source:** GNU Affero General Public License, version 3 or
  later (AGPL-3.0-or-later) — see [`LICENSE`](LICENSE).
- **Commercial:** a commercial license is available for proprietary
  or hosted use without AGPL obligations — see
  [`LICENSE-COMMERCIAL.md`](LICENSE-COMMERCIAL.md).

Releases up to and including **v0.2.0** were published under the
Apache License 2.0; the AGPL-3.0-or-later + commercial dual licensing
applies from the change recorded in `CHANGELOG.md` onward.
