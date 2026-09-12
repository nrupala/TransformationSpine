---
id: SR-0014
name: prompt-optimizer-agent
type: skill
status: verified
created: 2026-09-08
tags: [prompt-optimization, agents, spine, optimization]
location: D:\TransformationSpine\skills\prompt-optimizer-agent\SKILL.md
---

# Prompt Optimizer Agent

Optimizes prompt templates for TransformationSpine provider calls.

## Purpose

The prompt-optimizer-agent evaluates prompt templates against
transformation output and suggests improvements for clarity,
consistency, and effectiveness.

## Contract

1. **Evaluates prompts** — reviews prompt templates for clarity,
   specificity, and expected output structure.
2. **Suggests improvements** — returns concrete prompt changes.
3. **Validates output structure** — checks that prompts produce
   consistent structured output.
4. **Does not modify spine core** — agent skills operate independently.
5. **Returns optimization report** — suitable for review before
   deployment.

## Usage

```bash
spine agents prompt-optimize --input <path> --output <path>
```

## Implementation

- Entry point: `src/spine/agents/prompt_optimizer.py`
- Produces an optimization report with suggested changes
- Validates output structure against expected transformations
