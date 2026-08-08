# `pysindy:latest` — pysyndy base image

Shared base-image bundle for the `equation_recovery/pysindy` plugin. Not a
plugin itself: the build file is `Dockerfile.base`, so plugin discovery (which
keys on the exact name `Dockerfile`) skips this directory.

A thin layer over [`bind:latest`](../bind/README.md) that bakes in the
`submodules/pysyndy` recovery code. It reuses that image's Binary Ninja, Ghidra,
QEMU and PySR — no re-download, and no license needed at this step.

```bash
../bind/build.sh     # prerequisite: bind:latest must exist first
./build.sh           # -> pysindy:latest
```

`build.sh` stages the submodule's **tracked files at the pinned commit** (via
`git archive`) and drops the heavy or proprietary blobs the equation-recovery
core never needs — firmware fixtures, other-lab signatures, and the IDA/QEMU
corruption experiments — so the image stays lean.

`Dockerfile.base` also symlinks pysyndy's expected QEMU/FastDyn paths
(`/home/bind/pysyndy/qemu/build/...`, which `xbin_api._cfg_for` hard-codes) at
`bind:latest`'s Morpheus copies. pysyndy's own `qemu/` source is untracked, and
the two are the same BIND QEMU fork, so the dynamic collection runs without a
QEMU rebuild.

## Submodule

`submodules/pysyndy` (`git@github.com:PSecLab/pysyndy.git`, **private**, pinned
to `branch = main`), referenced by URL + commit SHA only. A fresh clone needs SSH
access to the private repo:

```bash
git submodule update --init submodules/pysyndy
```

The submodule stays at the repo root rather than moving in here: relocating a
submodule path rewrites `.gitmodules` and `.git/modules` and breaks every
existing clone until it re-inits.
