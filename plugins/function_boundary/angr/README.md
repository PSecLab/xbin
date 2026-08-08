# `angr_boundaries` — angr function boundary discovery

Discovers function start/end addresses with angr and posts them to
`function_boundary`.

- **Base image:** `python:3.11-slim` (self-contained)
- **Weight:** `0.90`
- **Competes with:** [`../radare/`](../radare/README.md) and
  [`../binja/`](../binja/README.md); judged by
  [`../boundary_ranker/`](../boundary_ranker/README.md) and checked by
  [`../boundary_validator/`](../boundary_validator/README.md).
