# `radare_cfg` — radare2 CFG generation

Builds a control-flow graph for the uploaded target with radare2 (r2pipe) and
posts it to `cfg_generation`.

- **Base image:** `python:3.11-slim` (self-contained; the orchestrator builds it)
- **Weight:** `0.85`
- **Competes with:** [`../angr/`](../angr/README.md)
