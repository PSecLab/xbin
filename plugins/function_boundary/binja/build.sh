#!/usr/bin/env bash
# Usage: ./build.sh [binja-install-dir] [license.dat]
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
conf() { sed -n "s/^$1: *//p" "$HERE/build.conf" | tr -d '"'; }

BINJA="${1:-$(conf 'binja dir')}"
LICENSE="${2:-$(conf 'license path')}"
TAG=xbin-plugin-function_boundary-binja

CTX="$HERE/.build_ctx"
rm -rf "$CTX"; mkdir -p "$CTX"
trap 'rm -rf "$CTX"' EXIT

cp -al "$BINJA" "$CTX/binaryninja" 2>/dev/null || cp -r "$BINJA" "$CTX/binaryninja"
cp "$LICENSE" "$CTX/license.dat"
cp -r "$HERE/../../../src" "$CTX/src"
# Morpheus seam + the analysis modules xbin_api.is_candidate() imports. Only the
# predicate half is used here (this image has BN but not the recovery stack).
cp "$HERE/../../../../pysyndy/xbin_api.py" "$CTX/xbin_api.py"
cp -r "$HERE/../../../../pysyndy/binja_scripts" "$CTX/binja_scripts"
cp "$HERE/binja_boundary_worker.py" "$HERE/Dockerfile" "$CTX/"

docker build ${NO_CACHE:+--no-cache} -t "$TAG" "$CTX"
echo "[+] built $TAG"
