<!-- Copyright 2026 Nrupal Akolkar -->
<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# Transformation Spine

[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/16398/badge)](https://www.bestpractices.dev/en/projects/16398)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/nrupala/TransformationSpine/badge)](https://scorecard.dev/viewer/?uri=github.com/nrupala/TransformationSpine)
[![REUSE status](https://api.reuse.software/badge/github.com/nrupala/TransformationSpine)](https://api.reuse.software/info/github.com/nrupala/TransformationSpine)

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

## Try it

**Fastest — the hosted demo:** a public demo of v0.3.0 runs at
[spine.aimlds.org](https://spine.aimlds.org). No install at all.

**Self-host — from a clone** (the package is not on PyPI and the GitHub
releases carry no binary assets; source is the install route today):

```bash
git clone https://github.com/nrupala/TransformationSpine.git
cd TransformationSpine
python -m pip install -e .
python spine_cli.py --port 8793 &   # bare invocation = serve mode
```

Then ask it who it is — real responses, captured from this release:

```bash
$ curl -s localhost:8793/api/v1/status
{"status":"ok","providers":[],"context_size":0,"ledger_entries":0,…,
 "tools":["calculator","current_time","echo"],
 "connectors":["azure-devops","confluence","databricks","github","jira","servicenow"],…}

$ curl -s localhost:8793/.well-known/agent-card.json
{"protocolVersion":"0.3.0","name":"transformationspine",
 "description":"Provider-neutral transformation spine: gated LLM cycles over a
 scoped, provenance-tracked context store, with a tamper-evident CTST ledger,…",
 "version":"0.3.1",…}
```

Agents connect over MCP (`POST /mcp`, Streamable HTTP — or
`python spine_cli.py mcp` for stdio), A2A (`POST /a2a`), or ACP
(`POST /acp/agents/{name}/runs`); see [docs/serving.md](docs/serving.md)
for every surface and [SKILL.md](SKILL.md) for the agent workflow.
A transform result carries its own verdict: the cycle's **error signal**
(0.0 = fully converged; anything above 0 means *not converged*) travels
with the output — a non-converged result is reported as one, never
dressed up as a success.

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

From a clone (see **Try it** above for the run commands that follow):

```bash
python -m pip install -e ".[dev]"
```

Run it: `python spine_cli.py` serves (bare invocation = serve mode);
`python spine_cli.py status|context|ledger|telemetry|providers|connector|workflow`
queries a running spine; `python spine_cli.py mcp` serves MCP over stdio
for subprocess-style agent hosts.

## Test / verify

```bash
python -m pytest tests
python -m ruff check src tests
python -m mypy src
```

## Status

v0.1.0 — Core spine with provider abstraction, context lifecycle, and a
CTST ledger.

v0.2.0 — Released 2026-10-09 after an independent audit and a full
remediation program (see `CHANGELOG.md` and `ASFQC/GATES.md`): 178 tests,
coverage held to a minimum of 80% in CI, CI green on Python 3.11 and
3.12. Serving surfaces: REST API, MCP (HTTP and stdio), an A2A agent
card, ACP runs, a browser UI, and the `spine` CLI. Connector
auto-discovery via entry points and plugin directories; a CTST ledger
with a verified hash chain; durable context persistence.

v0.3.0 — Released 2026-10-10. Closes the current development plan:
estimator calibration (the token engine now learns per-route
correction factors from estimate-vs-actual telemetry), a
certification package under `certification/` (manifest, certificate
TS-CERT-2026-001, test record — verify with
`python3 scripts/certify.py --check`), and a public demo running
this release at spine.aimlds.org.
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
