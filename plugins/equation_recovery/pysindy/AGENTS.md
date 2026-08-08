# AGENTS.md — the `pysindy` plugin

Recovers closed-form equations for floating-point leaf functions: Binary Ninja
structure analysis to find candidates, then numpy STLSQ sparse regression over
I/O pairs collected by running the firmware under QEMU/FastDyn.

See [`README.md`](README.md) and [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md).

## The `xbin_api` seam — the one rule

The **only** pysyndy surface this plugin may import is `xbin_api.py`, and only
its two sanctioned verbs:

```python
from xbin_api import is_candidate, recover_for_function
```

Everything else in pysyndy — `bind_auto`, `recover_equations`, the FastDyn/QEMU
invocation, the collection loop — stays behind that seam. Reaching past it
couples this plugin to pysyndy's internals and makes submodule bumps breaking
changes. If you need something the two verbs don't expose, extend `xbin_api`
upstream rather than importing around it.

pysyndy also ships its own `xbin_plugins/` (binja_boundary + equation_recovery +
morpheus), but those target a `function_boundary` + `symbol_matching` two-stage
model that this tree does not use. **They are unused here** — this plugin drives
the same `xbin_api` from its own self-contained `equation_recovery` plugin.

## What it needs

- A **non-stripped Cortex-M firmware ELF** with a `main` symbol and a
  vector-table section — `xbin_api` derives the bndb / VTOR / setup_end from it.
  On a raw `.bin` or a stripped target, BN discovery fails and the worker skips
  gracefully. This is why the plugin belongs to **no e2e tier**: the tiers'
  target is raw firmware.
- **`pysindy:latest`**, built by
  [`../../_bases/pysindy/build.sh`](../../_bases/pysindy/README.md) as a thin
  layer over `bind:latest`. It bakes in the pysyndy submodule's tracked files at
  the pinned commit, minus the heavy firmware/signature blobs.
- A **512M `/dev/shm`** for the dynamic run, declared as `shm_size = "1g"` in
  `xbin-plugin.toml` (Docker's 64M default is not enough).

## QEMU is symlinked, not built

`xbin_api._cfg_for` hard-codes pysyndy's QEMU/FastDyn at `<pysyndy>/qemu/build`,
but pysyndy's `qemu/` source is untracked. The base image symlinks those paths to
`bind:latest`'s Morpheus copies — same BIND QEMU fork, same FastDyn plugin, same
lineage — so the dynamic collection runs without a QEMU rebuild.

If a future pysyndy change diverges the QEMU ABI, build pysyndy's own QEMU in
`../../_bases/pysindy/Dockerfile.base` instead of symlinking.

## Submodule

`submodules/pysyndy` (`git@github.com:PSecLab/pysyndy.git`, **private**, pinned
to `branch = main`). Referenced by URL + commit SHA only — no vendored content —
so a public fork never carries pysyndy's code or firmware fixtures. A fresh clone
needs SSH access:

```bash
git submodule update --init submodules/pysyndy
```
