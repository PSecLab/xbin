# Testing the BIND plugin family

The tier definitions and prerequisites for the five plugins built on
`bind:latest`. For the generic harness — how tiers work, the dashboard
walkthrough, troubleshooting — see
[`docs/e2e_testing.md`](../../../docs/e2e_testing.md).

## Tiers

Declared per-plugin in each `xbin-plugin.toml`; `make tiers` prints what the
driver derives from them.

| Tier | Plugins | Question answered | Extra deps | Speed |
|---|---|---|---|---|
| `smoke` | `fid`, `ghidriff` | signature_matching | none (no ollama/QEMU) | minutes |
| `full`  | + `bind_se`, `bind_arbiter` | + equation_recovery | ollama (`qwen2.5-coder:7b`) | up to ~2h (angr) |
| `heavy` | + `symbolic_regression` | + PySR formulas | **QEMU/FastDyn in `bind:latest`** | hours |

`pysindy` is deliberately in no tier: it needs a non-stripped Cortex-M ELF, and
the tiers' raw `.bin` firmware target is not one. Start it by hand against a
suitable ELF.

## One-time setup

```bash
# 0. Populate the submodule (always the integration branch).
git submodule update --init --recursive --remote submodules/Morpheus
git -C submodules/Morpheus rev-parse --abbrev-ref HEAD    # -> integration

# 1. Build the base image (hours; needs a Binary Ninja install + license).
cp plugins/_bases/bind/build.conf.example plugins/_bases/bind/build.conf
$EDITOR plugins/_bases/bind/build.conf
plugins/_bases/bind/build.sh

# 2. The heavy tier additionally needs QEMU/FastDyn baked in; this verifies it.
plugins/_bases/bind/rebuild.sh

# 3. Check prerequisites for the tier you want.
scripts/preflight.sh --tier smoke        # or --tier heavy once QEMU is built

# 4. Stage the test firmware into uploads/.
plugins/_bases/bind/stage.sh             # or: make stage
```

`stage.sh` copies `gs3.bin` (2 MB ArduPilot single-image Cortex-M firmware) from
the Morpheus submodule into `uploads/`. A **copy**, not a symlink: `uploads/` is
bind-mounted into each worker container, and an external symlink would dangle
inside it.

No reference upload is needed for a smoke run — the symbolized reference and the
FID database are baked into `bind:latest`.

## Prerequisites by tier

`plugins/_bases/bind/preflight_checks.py` implements these; each prints its own
remediation when it fails.

| Check | Required for | Fix |
|---|---|---|
| `bind:latest` present | all tiers | `plugins/_bases/bind/rebuild.sh` |
| `bind_helpers` in the base (`/opt/xbin_bind`) | all tiers | `plugins/_bases/bind/build.sh --helpers-only` |
| QEMU + FastDyn inside the image | `heavy` | `plugins/_bases/bind/rebuild.sh` |
| ollama on `:11434` with `qwen2.5-coder:7b` | `full`, `heavy` | `ollama serve && ollama pull qwen2.5-coder:7b` |
| test firmware staged | (warning only) | `plugins/_bases/bind/stage.sh` |

## Running

```bash
scripts/e2e.sh smoke
scripts/e2e.sh full            # needs ollama
scripts/e2e.sh heavy           # needs QEMU in bind:latest
```

## Tool-specific notes

- **First fleet start is slow.** Each plugin builds as a `--no-cache` thin layer
  over the ~6.85 GB base — allow a few minutes per plugin.
- **`bind_se` is slow and low-yield on large firmware.** angr symbolic execution
  runs up to a 2h cap; on `gs3.bin` it posted only 2 hypotheses in ~39 h. Treat
  it as best-effort/secondary there; `symbolic_regression` is the practical
  `equation_recovery` producer. See [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) A and C.
- **`symbolic_regression` posting nothing** usually means no qualifying
  hardware-float functions, or QEMU missing from the base
  (`scripts/preflight.sh --tier heavy`).
- **No ✓ / no Validator badge is expected** — this family ships no
  `is_validator` plugin. The ✓ appears only when `fid` and `ghidriff` post
  identical data and deduplicate. Look for the **`Ranker: bind_arbiter`** badge
  instead.
- **Worker tunables.** `bind_se`'s fork-guard caps (`BIND_SE_FUNC_TIMEOUT`,
  default 90 s; `BIND_SE_FUNC_MEM_GB`, default 24) reach the container through
  the orchestrator's generic env allowlist:
  ```bash
  XBIN_WORKER_ENV_PASSTHROUGH=BIND_SE_FUNC_TIMEOUT,BIND_SE_FUNC_MEM_GB \
    BIND_SE_FUNC_TIMEOUT=1 xbin-orchestrator --no-browser
  ```
- **ELF vs raw `.bin`.** The Morpheus tools are a headerless-firmware toolchain
  and are strongest on raw `.bin` firmware; `prepare_config` converts an ELF
  upload to a raw flash image so they don't crash on it. `pysindy` is the
  ELF-native recoverer. See [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) E.
