---
id: SR-0013
name: test-generator-agent
type: skill
status: verified
created: 2026-09-08
tags: [test-generation, agents, spine, pytest]
location: D:\TransformationSpine\skills\test-generator-agent\SKILL.md
---

# Test Generator Agent

Generates syntactically valid pytest tests for TransformationSpine
transformations.

## Purpose

The test-generator-agent creates repeatable pytest tests for new
transformations and verifies generated tests compile and run.

## Contract

1. **Generates pytest code** — produces syntactically valid Python
   test modules.
2. **Validates generated tests** — runs py_compile and pytest on
   generated tests.
3. **Uses transformation context** — includes relevant fixtures and
   assertions based on the transformation output.
4. **Does not modify spine core** — agent skills operate independently.
5. **Returns generated tests and validation status**.

## Usage

```bash
spine agents test-generator --input <path> --output <path>
```

## Implementation

- Entry point: `src/spine/agents/test_generator.py`
- Generates pytest-compatible test files
- Runs `python -m pytest` on generated tests
