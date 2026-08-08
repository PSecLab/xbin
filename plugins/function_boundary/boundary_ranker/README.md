# `boundary_ranker` — function boundary ranker

The **ranker** for `function_boundary`. Reorders competing boundary hypotheses
with local heuristics — for example rewarding a finding that two specific
backends agree on.

Rankers are the only components allowed to set scores or ordering. With this
plugin running the category card shows a **`Ranker: boundary_ranker`** badge;
without it the category falls back to the baseline consensus math.

- **Base image:** `python:3.11-slim` (self-contained)
- **Weight:** `1.0`
