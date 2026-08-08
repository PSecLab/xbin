# `boundary_validator` — function boundary verifier

The **verifier** for `function_boundary`. Sanity-checks posted boundaries and
attaches an immutable `PASS` / `FAIL` / `ABSTAIN` stamp to the hypothesis it
judged.

Verifiers never modify scores or ordering — that is the ranker's job. A stamp
targets an explicit hypothesis id; the `"TOP"` alias is rejected, so a verdict
can never silently re-target as the blackboard reorders.

- **Base image:** `python:3.11-slim` (self-contained)
- **Weight:** `1.0`
