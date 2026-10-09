# TransformationSpine — Roadmap

Owned by Nrupal Akolkar. Status as of the v0.2.0 release (2026-10-09),
after the claim audit and remediation (see CHANGELOG).

## Shipped

- Context lifecycle core: scopes, promote/demote with provenance,
  session consolidation, durable backing for persisted scopes.
- Provider abstraction with adapters for llama.cpp, Ollama, OpenAI,
  HuggingFace (cloud + local), all behind one OpenAI-compatible layer.
- CTST ledger with a persisted, verifiable SHA-256 hash chain.
- Caller-side gate evaluation: deterministic error signals, every
  cycle ledgered with verdict + telemetry.
- Token-efficiency engine: route registry, token planner, two-tier
  cache-stable context assembly, compaction checkpoints
  (ENGINE-SPEC-v1, shared with the MyMilo engine).
- Profiles that route: local / cloud / hybrid via `spine.factory`,
  Routing.yaml, and SPINE_PROFILE.
- Tool registry + execution loop (`tools.yaml`, `spine.tools`).
- Six MCP-style connectors (GitHub, Azure DevOps, Jira, ServiceNow,
  Databricks, Confluence), mock-tested.
- Workflow authoring + execution (Mermaid, gates, cycle detection).
- Prebuilt agents: code review, test generation, prompt optimizer,
  lexical RAG.

## Next

- ~~Plugin-based connector auto-discovery~~ — shipped in the
  post-0.2.0 stack (entry points + directory plugins + registry).

- Composition with AxiomSpine and SpineLink (spine-stack): one
  context owner across the stack; TransformationSpine owns context and
  provider selection, AxiomSpine stays the dispatch/verification
  kernel.
- Estimator calibration: reconcile planned vs actual token counts in
  telemetry and adjust route margins automatically (engine slice 4).
- Vector retrieval backend for the RAG agent behind the same
  interface (lexical scorer remains the fallback).
- Plugin connector discovery via entry points (today connectors
  register by import).

## Non-goals

- No model-weight or attention-internals work; efficiency is an
  engine-layer property.
- No always-on cloud spend; cloud profiles activate only with keys
  the operator supplies.
