# `pysindy` — sparse regression equation recovery

Finds single-basic-block floating-point leaf functions with Binary Ninja,
collects I/O pairs by running the firmware under QEMU/FastDyn, and fits a closed
form with numpy STLSQ sparse regression. Fully automated — no pre-supplied
`.iopairs.txt`.

- **Base image:** `pysindy:latest` — see [`../../_bases/pysindy/`](../../_bases/pysindy/README.md)
- **Tiers:** none (see below)
- **`shm_size`:** `1g` for the dynamic run

## Requires a non-stripped Cortex-M ELF

`xbin_api` derives the bndb / VTOR / setup_end from the ELF's `main` symbol and
vector-table section. On a raw `.bin` or a stripped target, discovery fails and
the worker skips gracefully.

That is why `pysindy` belongs to **no e2e tier**: the tiers analyse raw firmware.
Start it by hand against a suitable ELF. It is the ELF-native recoverer of the
set — where the Morpheus tools are strongest on raw `.bin` firmware, `pysindy`
reads symbols and debug info directly.

```bash
plugins/_bases/bind/build.sh        # once
plugins/_bases/pysindy/build.sh     # once, after bind:latest
```

Development context — in particular the `xbin_api` two-verb seam this plugin must
not reach past — is in [`AGENTS.md`](AGENTS.md).
