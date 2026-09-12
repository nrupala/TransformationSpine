# Contributing to Transformation Spine

Thank you for considering a contribution. This project follows the Apache
Software Foundation methodology; every contribution must clear the ASF gates
recorded in `ASFQC/GATES.md`.

## Before you start

1. Read `spine.md` (vision) and `AGENT_CONTRACT.md` (how automated workers must
   behave here).
2. Read `ASFQC/GATES.md` — you are responsible for the gates touching your change.
3. Consult the decision log (`Decisions.md`) before making a decision; never
   overwrite an existing decision. Significant changes become new ADRs.

## Process

1. **Branch.** Work on a topic branch: `feat/<name>` or `fix/<name>`.
2. **Spec/plan first.** For non-trivial changes, describe the change and its
   acceptance oracle (how it will be verified) before writing code.
3. **Code.** Follow the existing style: typed Python 3.11+, `src/` layout,
   docstrings explaining the *why*.
4. **Verify.** The change is not done until these pass, with evidence recorded
   in `ASFQC/GATES.md`:
   ```bash
   python -m pytest tests -q
   python -m ruff check src tests
   python -m mypy src
   ```
5. **Gate evidence.** Append the observed command output / exit codes to the
   gate tracker. A gate is PASS only with recorded evidence.
6. **Commit.** Conventional Commits style (`feat:`, `fix:`, `docs:`, `test:`).
   Never commit secrets, keys, or `.env` files.
7. **Release note.** Add a `CHANGELOG.md` entry for user-visible changes.

## Definition of done

A contribution is done only when: tests pass, lint/typecheck clean, gate
tracker updated with evidence, decision log updated if a decision changed, and
the tree has no scratch files, secrets, or unrelated changes.

## Code of conduct

See `CODE_OF_CONDUCT.md`. In short: be professional, assume good faith, and
treat safety-critical discipline as the baseline — this project targets
high-assurance systems.