#!/usr/bin/env bash
# Build `pysindy:latest` = `bind:latest` + the pysyndy submodule's recovery code
# baked in. Binary Ninja / QEMU / FastDyn / Ghidra / PySR / numpy are reused from
# bind:latest, so this only layers the pysyndy Python tree onto PYTHONPATH -- no
# re-download, no Binary Ninja license needed here (it is already baked into
# bind:latest). The thin plugin plugins/equation_recovery/pysindy/ builds FROM
# this image (in-tree, by the orchestrator).
#
# Prereq: plugins/_bases/bind/build.sh must have produced bind:latest first.
# Usage:  plugins/_bases/pysindy/build.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
PYSINDY_DIR="$REPO_ROOT/submodules/pysyndy"
IMAGE="${PYSINDY_IMAGE:-pysindy:latest}"
BASE="${BIND_IMAGE:-bind:latest}"

# --- Ensure base image + submodule are present -----------------------------
docker image inspect "$BASE" >/dev/null 2>&1 || {
  echo "Base image '$BASE' missing -- run plugins/_bases/bind/build.sh first" >&2; exit 1; }
if [[ ! -d "$PYSINDY_DIR/binja_scripts" ]]; then
  echo "[*] Initializing pysyndy submodule..."
  git -C "$REPO_ROOT" submodule update --init submodules/pysyndy
fi

# --- Keep the (large) staging context off the small root /tmp --------------
export TMPDIR="${TMPDIR:-$REPO_ROOT/.xbin_scratch}"
mkdir -p "$TMPDIR"
BUILD_CTX="$(mktemp -d -t pysindy-build-XXXXXX)"
trap 'rm -rf "$BUILD_CTX"' EXIT

echo "[+] Staging pysyndy code (tracked files at the pinned commit) into $BUILD_CTX"
mkdir "$BUILD_CTX/pysyndy"
# `git archive` emits only tracked files at HEAD (the submodule's pinned commit).
git -C "$PYSINDY_DIR" archive HEAD | tar -x -C "$BUILD_CTX/pysyndy"
# Drop heavy/proprietary blobs the equation-recovery core never needs (firmware
# fixtures, other-lab signatures, IDA/QEMU-corruption experiments). Keeps the
# image lean and avoids baking proprietary firmware into it.
rm -rf "$BUILD_CTX/pysyndy/example_config" \
       "$BUILD_CTX/pysyndy/hitl" \
       "$BUILD_CTX/pysyndy/ida_scripts" \
       "$BUILD_CTX/pysyndy/clibtest" \
       "$BUILD_CTX/pysyndy/qpr8_corrupt" \
       "$BUILD_CTX/pysyndy/signature_matching"

echo "[+] Building $IMAGE FROM $BASE ..."
docker build --build-arg "BASE=$BASE" -f "$HERE/Dockerfile.base" -t "$IMAGE" "$BUILD_CTX"
echo "[+] Built $IMAGE. The pysindy plugin builds FROM this image."
