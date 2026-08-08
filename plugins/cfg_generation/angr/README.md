# `angr_cfg` — angr CFG generation

Builds a control-flow graph for the uploaded target with angr and posts it to
`cfg_generation`.

- **Base image:** `python:3.11-slim` (self-contained; the orchestrator builds it)
- **Weight:** `0.90`
- **Competes with:** [`../radare/`](../radare/README.md) — both post a graph with
  `nodes` and `edges` for the same item key, and the blackboard scores them
  against each other.
