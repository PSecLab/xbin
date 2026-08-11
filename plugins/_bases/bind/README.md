# `bind:latest` — the Morpheus/BIND base image

Shared base-image bundle for the BIND plugin family. It is not a plugin: the
orchestrator discovers plugins by walking for a file named exactly `Dockerfile`,
and everything here is named `Dockerfile.base`, so this directory never appears
on the dashboard.

Five plugins across two categories build `FROM bind:latest`:

| Category | Plugin | What it answers |
|---|---|---|
| `signature_matching` | `fid` | Ghidra Function ID matching |
| `signature_matching` | `ghidriff` | ghidriff / BSim binary diffing |
| `signature_matching` | `bind_arbiter` | **ranker** — reconciles competing identifications via a local LLM |
| `equation_recovery` | `bind_se` | angr symbolic execution + LLM explanation |
| `equation_recovery` | `symbolic_regression` | PySR symbolic regression + LLM explanation |

A sixth, `equation_recovery/pysindy`, builds on `pysindy:latest`, which is itself
a thin layer over this image — see [`../pysindy/`](../pysindy/README.md).

Item keys are function addresses (`norm_addr` → `0x%08x`), so every tool posts
hypotheses for the same function side-by-side and the blackboard can compare
them directly.

## Contents

| File | Purpose |
|---|---|
| `build.sh` | Builds the image. Two stages — see below. |
| `Dockerfile.base` | Stage 2: the thin xbin layer (adds `bind_helpers.py`). |
| `rebuild.sh` | Guarded rebuild + verify wrapper (kills stale instances, checks QEMU landed). |
| `build.conf.example` | Template for `build.conf` (gitignored — it names your local Binary Ninja install). |
| `bind_helpers.py` | Python helpers shared by all BIND workers; baked in at `/opt/xbin_bind`. |
| `preflight_checks.py` | This family's readiness checks, discovered by `xbin_orchestrator/preflight.py`. |
| `stage.sh` | Stages the test firmware into `uploads/`. |
| `KNOWN_ISSUES.md` | Issue log for these tools. |
| `TESTING.md` | Tier definitions and the BIND-specific end-to-end walkthrough. |

## Building

```bash
cp build.conf.example build.conf     # then fill in your Binary Ninja paths
./build.sh                           # both stages (hours)
./build.sh --helpers-only            # stage 2 only (seconds)
./rebuild.sh [--force]               # guarded rebuild, verifies QEMU is present
```

The build is deliberately split in two:

1. **`bind-morpheus:latest`** — built directly from
   `submodules/Morpheus/docker/Dockerfile`: Ghidra + Binary Ninja + the QEMU fork
   + PySR + the Morpheus tree at `/home/bind/Morpheus`. Multi-hour.
2. **`bind:latest`** — `Dockerfile.base`, a thin layer that copies
   `bind_helpers.py` to `/opt/xbin_bind`. Seconds.

Editing the shared helpers therefore costs a one-file layer rebuild rather than
a full base rebuild. If you are upgrading from a single-stage image, running
`./build.sh --helpers-only` adopts the existing `bind:latest` as stage 1 rather
than rebuilding it.

The image bakes in a Binary Ninja install **and its license** — keep it local,
never push it.

> **Rebuilding this image invalidates every image derived from it.**
> `pysindy:latest` is built `FROM bind:latest`, so a rebuild here leaves it
> stale — it keeps the *old* contents while plugin Dockerfiles reference the new
> ones, and the affected worker dies at import with a bare `ModuleNotFoundError`
> that points nowhere near the real cause. After any rebuild here, also run:
>
> ```bash
> ../pysindy/build.sh
> ```
>
> `make preflight` catches this: the pysindy bundle's `preflight_checks.py`
> compares the two images' build timestamps and verifies the inherited files are
> actually present.

> **Do not** use the submodule's `docker/build_docker.sh`: it is stale (it
> references a non-existent `Dockerfile.bind` and reads a `gemini.key`).
> `build.sh` uses the real `Dockerfile` and passes no Gemini key — xbin drives a
> local ollama for every LLM step.

## `bind_helpers.py`

This module used to live in `src/xbin/`, the SDK package. That was wrong: the
orchestrator injects all of `src/` into *every* plugin build context, so a
`radare_cfg` image was carrying Morpheus helpers it could never use. It belongs
to this base image, which reaches only the plugins built `FROM bind:latest`.

Each BIND plugin's Dockerfile puts `/opt/xbin_bind` on `PYTHONPATH`, so workers
`import bind_helpers` directly. It provides:

- `prepare_config()` — builds the per-run `bind_config.toml`, including the
  ELF → raw Cortex-M flash conversion (see KNOWN_ISSUES issue E).
- `function_universe()` / `get_func_intersection()` — the BN ∩ Ghidra function
  universe every tool iterates.
- `CAT_SIGNATURE` / `CAT_EQUATION` — the two category constants.

Every Morpheus import inside it is deferred into a function, so the module
imports fine on a dev box without the heavy stack — which is what lets the test
suite load the workers without Docker.

## How the workers run the analysis

Each worker reacts to `NEW_BINARY`, builds a per-run config via
`prepare_config`, computes the BN ∩ Ghidra function universe, and drives the
corresponding Morpheus client's `setup()` / `handle(func)` **directly**,
bypassing Morpheus's own HTTP job server (`bind_integration.py`). Without that
server `JobClient.is_cancelled()` safely returns `False`, so the clients just run
to completion.

## Submodule

`submodules/Morpheus` (`git@github.com:purseclab/Morpheus.git`) backs all five
plugins. **Always the `integration` branch** — `.gitmodules` pins
`branch = integration`, and `build.sh` checks it out before building.

```bash
git submodule update --init --recursive --remote submodules/Morpheus
```

The submodule stays at the repo root rather than moving in here, because
relocating a submodule path rewrites `.gitmodules` and `.git/modules` and breaks
every existing clone until it re-inits. Ownership is documented here instead.

Note: the submodule's `docker/run_bind_integration.sh` hardcodes a
`GEMINI_API_KEY` default and `build_docker.sh` reads a `gemini.key`. xbin uses
ollama and never propagates either, but that key should be rotated upstream.

Editing files under `submodules/Morpheus/` creates a local submodule diff that a
later `git submodule update` may reset. Track intended Morpheus changes upstream
(purseclab/Morpheus, `integration` branch) or re-apply them after updates.

## Runtime requirements

- **ollama** on `:11434` with `qwen2.5-coder:7b`, for `bind_se`/`symbolic_regression`
  explanations and the arbiter. Workers run with `--network host`, so they reach
  a host ollama at `http://127.0.0.1:11434/v1`.
- **QEMU/FastDyn inside the image**, for `symbolic_regression`'s dynamic run.
  `./rebuild.sh` verifies it landed.
- The stack is tuned for **ARM Cortex-M firmware** (`ARM:LE:32:Cortex`, VTOR load
  address, FP-function filtering).

## Reference binaries

`ghidriff` and `bind_se` match against a symbolized reference. On upload the
orchestrator saves an optional uploaded reference as `<binary-stem>.reference`
next to the target (a generic sibling convention it applies for any plugin);
`prepare_config` also picks up a `<stem>.fidb`. Absent an upload, the baked
arducopter defaults are used.
