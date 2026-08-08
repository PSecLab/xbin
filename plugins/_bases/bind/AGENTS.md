# AGENTS.md — the Morpheus/BIND family

Context for the five plugins that build `FROM bind:latest` (`fid`, `ghidriff`,
`bind_arbiter`, `bind_se`, `symbolic_regression`) and for this base bundle
itself. See [`README.md`](README.md) for the layout,
[`TESTING.md`](TESTING.md) for the tiers, and
[`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) for the issue log.

This directory is **not a plugin** — its build file is named `Dockerfile.base`
precisely so plugin discovery (which keys on the exact name `Dockerfile`) skips
it.

## The two-stage build

```bash
./build.sh                 # stage 1 (bind-morpheus:latest, hours) + stage 2
./build.sh --helpers-only  # stage 2 only (seconds)
./rebuild.sh [--force]     # guarded rebuild; kills stale instances, verifies QEMU
```

1. **`bind-morpheus:latest`** — built directly from
   `submodules/Morpheus/docker/Dockerfile`: Ghidra + Binary Ninja + the QEMU fork
   + PySR + the Morpheus tree at `/home/bind/Morpheus`.
2. **`bind:latest`** — `Dockerfile.base`, a thin layer copying `bind_helpers.py`
   to `/opt/xbin_bind`.

Edit `bind_helpers.py` → `--helpers-only` is all you need. `--helpers-only` also
adopts an existing single-stage `bind:latest` as stage 1, so upgrading costs
seconds rather than a rebuild.

**Rebuilding `bind:latest` invalidates the images derived from it.**
`pysindy:latest` is `FROM bind:latest`; if you rebuild here and not there, the
pysindy worker dies at `import bind_helpers` because its base predates the
`/opt/xbin_bind` layer — a failure whose message says nothing about staleness.
Always follow a rebuild here with `../pysindy/build.sh`. The pysindy bundle's
`preflight_checks.py` exists specifically to catch this (timestamp comparison +
a direct check that the inherited files are present).

**Do not** use the submodule's `docker/build_docker.sh` — it is stale (references
a non-existent `Dockerfile.bind`, reads a `gemini.key`). `build.sh` uses the real
`Dockerfile` and passes no Gemini key; xbin drives a local ollama.

The image bakes in Binary Ninja **and its license**. Keep it local, never push
it. `build.conf` is gitignored; only `build.conf.example` is tracked.

## `bind_helpers.py` lives here, not in the SDK

It used to be `src/xbin/bind_helpers.py`, which meant every unrelated plugin
image carried Morpheus code (the orchestrator injects all of `src/` into every
plugin build context). It belongs to this base image, which reaches only the
plugins built on it. Workers `import bind_helpers`; their Dockerfiles put
`/opt/xbin_bind` on `PYTHONPATH`.

Keep every Morpheus import deferred inside a function. The orchestrator and the
test suite import worker modules statically to read their metadata, and must be
able to do so on a dev box with no Ghidra, no Binary Ninja and no submodule.

## Submodule

`submodules/Morpheus` (`git@github.com:purseclab/Morpheus.git`), **always the
`integration` branch** — `.gitmodules` pins it and `build.sh` checks it out
before building.

Editing files under `submodules/Morpheus/` creates a local submodule diff that a
later `git submodule update` may reset. Track intended changes upstream
(purseclab/Morpheus, `integration`) or re-apply after updates. The running
`bind:latest` has historically carried COPY-layer patches for exactly this
reason — see the "Notes for future rebuilds" section in `KNOWN_ISSUES.md` before
assuming the image matches the submodule source.

The submodule's `docker/run_bind_integration.sh` hardcodes a `GEMINI_API_KEY`
default. xbin never propagates it, but it should be rotated upstream.

## How the workers run

Each worker reacts to `NEW_BINARY`, builds a per-run `bind_config.toml` via
`prepare_config`, computes the BN ∩ Ghidra function universe, and drives the
Morpheus client's `setup()` / `handle(func)` **directly** — bypassing Morpheus's
own HTTP job server (`bind_integration.py`). Without that server
`JobClient.is_cancelled()` safely returns `False`, so the clients run to
completion.

Item keys are function addresses (`norm_addr` → `0x%08x`), so every tool posts
hypotheses for the same function side-by-side.

## Things that have bitten us before

- **Fork after threads.** `function_universe()` loads Binary Ninja *and* an
  in-process Ghidra JVM (~118 threads). Anything that `fork()`s afterwards
  deadlocks. `bind_se_worker._function_universe_isolated()` runs the universe
  computation in a throwaway subprocess for this reason — don't inline it back.
- **`force_complete_scan` on a multi-MB blob** explodes memory (~47 GiB observed).
  Seed the CFG with the known function starts instead. See KNOWN_ISSUES #5.
- **The `ghidra_scripts/` exclude glob** in `build.sh` is `./ghidra_[0-9]*`, not
  `./ghidra_*`. The looser glob silently drops `ghidra_scripts/` and breaks the
  function universe at runtime. See KNOWN_ISSUES #2.
- **ELF uploads.** These tools are a headerless-firmware toolchain and assume a
  raw Cortex-M `.bin`. `prepare_config` converts an ELF to a raw flash image
  first. They are strongest on raw firmware; `pysindy` is the ELF-native
  recoverer. See KNOWN_ISSUES E.
- **Worker tunables** (`BIND_SE_FUNC_TIMEOUT`, `BIND_SE_FUNC_MEM_GB`) reach the
  container only through the operator's generic allowlist
  `XBIN_WORKER_ENV_PASSTHROUGH`. Do not add their names to the orchestrator.
- The stack is tuned for **ARM Cortex-M** (`ARM:LE:32:Cortex`, VTOR load address,
  FP-function filtering).
