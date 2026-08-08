# Known issues — `pysindy`

See [`README.md`](README.md) for what this plugin is and
[`../../_bases/pysindy/`](../../_bases/pysindy/README.md) for the base image it
builds on.

## Open

### pysindy is automated now; needs a non-stripped firmware ELF — NOTE
The `pysindy` plugin (`equation_recovery`, from `submodules/pysyndy`) drives
pysyndy's **automated** pipeline via `xbin_api` (`is_candidate` + `recover_for_function`):
it discovers single-basic-block FP-leaf functions and, per function, **collects I/O
pairs by running the firmware under QEMU/FastDyn**, then fits — no pre-supplied
`.iopairs.txt`. (Superseded the earlier sibling-iopairs v1.) Verified on `sample.axf`
(4/5 candidates recovered, all `verified=True`, R²≈1.0, e.g. `+35*sqrt(x) +5*x*sqrt(x)`).

Requirements/limits:
- Needs a **non-stripped Cortex-M firmware ELF** with a `main` symbol + a vector-table
  section — `xbin_api` derives the bndb/VTOR/setup_end from it. On a raw `.bin` or a
  stripped target the BN discovery fails and the worker skips gracefully.
- QEMU/FastDyn is reused from bind:latest's Morpheus fork via symlinks baked by
  `../../_bases/pysindy/Dockerfile.base` (pysyndy's own `qemu/` source is untracked). If a future
  pysyndy change diverges the QEMU ABI, build pysyndy's own base instead.
- The dynamic run needs a 512M `/dev/shm`, declared as `shm_size = "1g"` in this
  plugin's `xbin-plugin.toml` (Docker's 64M default is not enough).
