<!-- Copyright 2026 Nrupal Akolkar -->
<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
# Transformation Spine

## Purpose

Maintain continuity independent of any model.

Models are workers.

The spine owns:

- context
- memory
- decisions
- governance
- knowledge
- provider selection

---

## Current Goal

Create a provider neutral transformation platform.

Success Criteria:

- Switch providers without losing memory
- Persistent architecture knowledge
- Decision traceability
- MCP support
- ACP support

---

## Transformation Principles

1. Memory before prompting
2. Decisions before execution
3. Governance before automation
4. Context before reasoning
5. Portability before optimization

---

## Approved Providers

- OpenAI
- Anthropic
- Ollama

---

## Routing Policy

Coding:
Claude

Architecture:
GPT

Large Context Analysis:
Claude

Local Sensitive Data:
Ollama

Fallback:
GPT
