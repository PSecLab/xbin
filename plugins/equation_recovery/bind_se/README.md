# `bind_se` — symbolic execution

Recovers what a function computes by running angr symbolic execution over it and
turning the resulting expression into readable text with a local LLM. Posts
semantics to `equation_recovery` and any identity matches it finds to
`signature_matching`.

- **Base image:** `bind:latest` — see [`../../_bases/bind/`](../../_bases/bind/README.md)
- **Tiers:** `full`, `heavy`
- **Extra services:** ollama on `:11434` with `qwen2.5-coder:7b`

## Operational notes

`bind_se` is the slowest and lowest-yield producer in the family on large
firmware — on a 2 MB image it posted 2 hypotheses in ~39 h. Treat it as
best-effort; `symbolic_regression` is the practical `equation_recovery` producer
at that size. It performs far better on smaller targets.

Two tunables bound the per-function loop, forwarded through the orchestrator's
generic env allowlist:

```bash
XBIN_WORKER_ENV_PASSTHROUGH=BIND_SE_FUNC_TIMEOUT,BIND_SE_FUNC_MEM_GB \
  BIND_SE_FUNC_TIMEOUT=90 BIND_SE_FUNC_MEM_GB=24 xbin-orchestrator --no-browser
```

The worker computes its function universe in a throwaway subprocess
(`_function_universe_isolated`) — do not inline that back, it exists to avoid a
fork-after-threads deadlock. See
[`../../_bases/bind/KNOWN_ISSUES.md`](../../_bases/bind/KNOWN_ISSUES.md) #5–#7.
