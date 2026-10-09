---
id: SR-0012
name: code-review-agent
type: skill
status: verified
created: 2026-09-08
tags: [code-review, agents, spine, transformation, testing]
location: skills/code-review-agent/SKILL.md
---

# Code Review Agent

Automates code review on TransformationSpine transformation output.

## Purpose

The code-review-agent provides automated review of transformation
output, checking for SOLID violations, code smells, lint errors, and
security issues in generated code artifacts.

## Contract

1. **Triggered on transformation output** — reviews all files produced
   by spine transformations.
2. **Checks for common issues**: unused imports, type errors, lint
   failures, and security patterns.
3. **Generates review reports** in structured format (JSON/markdown).
4. **Does not modify spine core** — agent skills operate independently.
5. **Returns pass/fail with details** — suitable for CI integration.

## Usage

```bash
spine agents code-review --output <path>
```

## Implementation

- Entry point: `src/spine/agents/code_review.py`
- Uses `ruff`, `mypy`, and `pytest` for validation
- Produces a JSON review report at the specified output path
