# `symbolic_regression` — PySR symbolic regression

Filters the target to hardware-float functions, runs each under QEMU to collect
input/output pairs, then recovers a closed-form formula with PySR and explains it
with a local LLM. The highest-weighted `equation_recovery` producer, and the
practical one on large firmware.

- **Base image:** `bind:latest` — see [`../../_bases/bind/`](../../_bases/bind/README.md)
- **Tiers:** `heavy`
- **Extra services:** ollama on `:11434`; **QEMU/FastDyn inside the base image**
- **`shm_size`:** `1g` — the system-mode guest backs its RAM with a 512M
  `/dev/shm` file, and Docker's 64M default is not enough

The QEMU requirement is what makes this the heavy tier. Verify it landed:

```bash
make preflight TIER=heavy      # or: plugins/_bases/bind/rebuild.sh
```

Posting nothing usually means no qualifying float functions in the target, or
QEMU missing from the base image — check the container **Logs** either way.
