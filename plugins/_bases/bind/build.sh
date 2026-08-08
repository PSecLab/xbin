#!/usr/bin/env bash
# Build the self-contained `bind:latest` base image that the BIND plugin family
# extends (fid, ghidriff, bind_arbiter, bind_se, symbolic_regression -- and,
# transitively, pysindy via plugins/_bases/pysindy).
#
# Two stages:
#   1. `bind-morpheus:latest` -- the heavy image, built directly from
#      submodules/Morpheus/docker/Dockerfile (Ghidra + Binary Ninja + the QEMU
#      fork + PySR + the Morpheus tree at /home/bind/Morpheus). Hours.
#   2. `bind:latest` -- Dockerfile.base, a thin layer adding this bundle's
#      shared bind_helpers.py. Seconds.
#
# Splitting them means a helper edit does not cost a full base rebuild. Pass
# --helpers-only to redo just stage 2.
#
# We deliberately do NOT use submodules/Morpheus/docker/build_docker.sh -- it is
# stale (references a non-existent Dockerfile.bind and reads a gemini.key). We
# also do NOT pass a Gemini key: xbin uses a local ollama for all LLM steps.
#
# Usage:
#   plugins/_bases/bind/build.sh [<binaryninja-dir-or-zip>] [<license.dat>]
#   plugins/_bases/bind/build.sh --helpers-only
#
# Missing args fall back to this directory's build.conf (copy build.conf.example
# to build.conf and fill it in). The Binary Ninja install and license are baked
# into the image, so keep the resulting image local -- do not push it.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
MORPHEUS_DIR="$REPO_ROOT/submodules/Morpheus"
DOCKER_DIR="$MORPHEUS_DIR/docker"
DOCKERFILE="$DOCKER_DIR/Dockerfile"
IMAGE="${BIND_IMAGE:-bind:latest}"
STAGE1="${BIND_STAGE1_IMAGE:-bind-morpheus:latest}"

conf() {  # read a "label: value" line from build.conf (quotes/space trimmed, ~ expanded)
  local v
  v="$(sed -n "s/^[[:space:]]*$1[[:space:]]*:[[:space:]]*//p" "$HERE/build.conf" 2>/dev/null \
        | head -n1 | sed -e 's/[[:space:]]*$//' -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/")"
  printf '%s' "${v/#\~/$HOME}"
}

# --- stage 2: the thin xbin layer -------------------------------------------
build_helpers_layer() {
  echo "[+] Layering xbin bind helpers onto $STAGE1 -> $IMAGE"
  docker build --build-arg "BIND_STAGE1=$STAGE1" \
               -f "$HERE/Dockerfile.base" -t "$IMAGE" "$HERE"
  echo "[+] Built $IMAGE. The BIND plugins build FROM this image."
}

if [[ "${1:-}" == "--helpers-only" ]]; then
  if ! docker image inspect "$STAGE1" >/dev/null 2>&1; then
    # Migration path for an image built before the build was split in two: an
    # existing bind:latest IS a valid stage 1, so adopt it rather than making
    # the user sit through a multi-hour rebuild for a one-file layer.
    if docker image inspect "$IMAGE" >/dev/null 2>&1; then
      echo "[*] No $STAGE1; adopting the existing $IMAGE as stage 1."
      docker tag "$IMAGE" "$STAGE1"
    else
      echo "[x] Neither $STAGE1 nor $IMAGE exists -- run this script with no args first." >&2
      exit 1
    fi
  fi
  build_helpers_layer
  exit 0
fi

BINJA_DIR="${1:-$(conf 'binja dir')}"
LICENSE="${2:-$(conf 'license path')}"

# --- Ensure the submodule is present and on the integration branch ----------
if [[ ! -f "$DOCKERFILE" ]]; then
  echo "[*] Initializing Morpheus submodule..."
  git -C "$REPO_ROOT" submodule update --init --recursive submodules/Morpheus
fi
CUR_BRANCH="$(git -C "$MORPHEUS_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo DETACHED)"
if [[ "$CUR_BRANCH" != "integration" ]]; then
  echo "[!] Morpheus is on '$CUR_BRANCH'; checking out 'integration' (xbin always uses integration)."
  git -C "$MORPHEUS_DIR" fetch origin integration --quiet || true
  git -C "$MORPHEUS_DIR" checkout integration
fi

# --- Validate inputs --------------------------------------------------------
[[ -f "$HERE/build.conf" || -n "${1:-}" ]] \
  || echo "[!] No $HERE/build.conf -- copy build.conf.example to build.conf and fill it in."
[[ -n "$BINJA_DIR" && -e "$BINJA_DIR" ]] || { echo "Binary Ninja install not found: '$BINJA_DIR' (set it in $HERE/build.conf or pass as arg 1)" >&2; exit 1; }
[[ -n "$LICENSE"   && -f "$LICENSE"   ]] || { echo "license.dat not found: '$LICENSE' (set it in $HERE/build.conf or pass as arg 2)" >&2; exit 1; }

# --- Stage the build context (Dockerfile COPYs Morpheus/, binaryninja/, license.dat) ---
# Keep the (large) staging context off the small root /tmp: default TMPDIR to a
# repo-local scratch dir on the big disk unless the caller already set one.
export TMPDIR="${TMPDIR:-$REPO_ROOT/.xbin_scratch}"
mkdir -p "$TMPDIR"
BUILD_CTX="$(mktemp -d -t bind-build-XXXXXX)"
trap 'rm -rf "$BUILD_CTX"' EXIT

echo "[+] Staging build context at $BUILD_CTX"
cp "$DOCKERFILE" "$BUILD_CTX/Dockerfile"

if [[ "$BINJA_DIR" == *.zip ]]; then
  echo "[+] Unzipping Binary Ninja..."
  unzip -q "$BINJA_DIR" -d "$BUILD_CTX"
  [[ -d "$BUILD_CTX/binaryninja" ]] || { echo "Expected 'binaryninja/' at the top level of the zip" >&2; exit 1; }
else
  cp -a "$BINJA_DIR" "$BUILD_CTX/binaryninja"
fi
cp "$LICENSE" "$BUILD_CTX/license.dat"

# Copy the Morpheus tree without the heavy/regenerated bits the image rebuilds.
# NB: the ghidra exclude is deliberately './ghidra_[0-9]*' (a versioned Ghidra
# *install*), not './ghidra_*' -- the latter also swallows ghidra_scripts/,
# which the function-universe helpers need at runtime.
mkdir "$BUILD_CTX/Morpheus"
tar -C "$MORPHEUS_DIR" \
    --exclude='./.git' \
    --exclude='./qemu' \
    --exclude='./ghidra_[0-9]*' \
    --exclude='./docker/binaryninja' \
    --exclude='./docker/license.dat' \
    -cf - . | tar -C "$BUILD_CTX/Morpheus" -xf -

# --- stage 1: the heavy Morpheus image (no Gemini key: ollama-only) ----------
echo "[+] Building $STAGE1 (this is heavy: Binary Ninja + Ghidra + QEMU + PySR)..."
docker build --build-arg GEMINI_API_KEY="" -f "$BUILD_CTX/Dockerfile" -t "$STAGE1" "$BUILD_CTX"

build_helpers_layer
