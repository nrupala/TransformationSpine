<!-- Copyright 2026 Nrupal Akolkar -->
<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
┌─────────────────────────────────────────────────────────────────┐
│                    Spine Portal                                   │
│                                                                  │
│  Web UI (NextJS)  |  Claude Desktop  |  OpenCode  |  VS Code     │
│  Teams/Copilot (optional)  |  CLI (spine_cli)  |  MCP clients    │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Spine API (FastAPI)                            │
│                                                                  │
│  /transform   /context   /ledger   /status   /telemetry          │
│  Authentication  |  Context APIs  |  Decision APIs               │
│  Memory APIs  |  Task APIs  |  Provider APIs  |  Connector APIs  │
└───────────────────────────────┬─────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│ Decision Store  │   │   Task Store    │   │  Memory Store   │
│    (Postgres)   │   │    (Postgres)   │   │    (Postgres)   │
└─────────────────┘   └─────────────────┘   └─────────────────┘
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Vector Knowledge (Qdrant)                        │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                Provider Router Layer                             │
│                                                                  │
│  LOCAL MODE         CLOUD MODE         HYBRID MODE               │
│  ──────────         ──────────         ───────────               │
│  LlamaCpp          OpenAI/Azure       Complex→Cloud              │
│  Ollama(offline)   HuggingFace        Simple→Local               │
│  OpenAI compat     Anthropic          Fallback chains            │
└───────────────────────┬─────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  Claude     │  │  OpenAI     │  │  Ollama     │
│  Sonnet     │  │  GPT/Claude │  │  DeepSeek   │
│  Other      │  │  Azure      │  │  Local      │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │               │               │
       └───────────────┼───────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│              MCP/ACP Connector Layer (Plugin Framework)          │
│                                                                  │
│  GitHub  │  Azure DevOps  │  Jira  │  ServiceNow  │           │
│  Databricks │  Confluence │  SharePoint │  Power Platform    │
│  AWS (S3/Lambda/Bedrock)  │  GCP (Vertex/Storage)  │  Oracle   │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│              ACP Agent Layer (Prebuilt Agents)                   │
│                                                                  │
│  Architecture Agent  │  Research Agent  │  Delivery Agent        │
│  Governance Agent    │  Code Review Agent │  Test Generator      │
│  Prompt Optimizer    │  RAG Pipeline Agent                      │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│              Audit & Telemetry Layer                             │
│                                                                  │
│  CTST Ledger (hash-chained JSONL)  │  /telemetry endpoint       │
│  Error signals  │  Convergence metrics  │  Usage analytics      │
│  Provider latency  │  Token usage  │  Scope promotion counts    │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│              OS-Level Safeguarding (No Docker)                    │
│                                                                  │
│  Least-privilege file access  │  Read-only source directories    │
│  Write-restricted paths  │  Backup-before-write enforcement     │
│  WSL/bwrap sandboxing  │  Path confinement                    │
└─────────────────────────────────────────────────────────────────┘