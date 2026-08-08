#!/usr/bin/env bash
# Build this plugin's image out-of-band.
#
# The image bakes in a ~1.2 GB Binary Ninja install AND a license, which is why
# the plugin carries a `.xbin-prebuilt` marker: the orchestrator will not build
# it for you, it only reuses the image this script produces. If you saw
#
#   "binja/function_boundary is marked .xbin-prebuilt but image
#    'xbin-plugin-function_boundary-binja' is missing -- run .../build.sh first"
#
# then you are in the right place: the image has never been built on this host.
#
# Usage:
#   ./build.sh [<binaryninja-dir-or-zip>] [<license.dat>]
#
# Missing args fall back to ./build.conf -- copy build.conf.example to
# build.conf and fill it in. Keep the resulting image local; never push it.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
TAG=xbin-plugin-function_boundary-binja

conf() {  # read a "label: value" line from build.conf (quotes/space trimmed, ~ expanded)
  local v
  v="$(sed -n "s/^[[:space:]]*$1[[:space:]]*:[[:space:]]*//p" "$HERE/build.conf" 2>/dev/null \
        | head -n1 | sed -e 's/[[:space:]]*$//' -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/")"
  printf '%s' "${v/#\~/$HOME}"
}

if [[ ! -f "$HERE/build.conf" && $# -eq 0 ]]; then
  echo "[x] No $HERE/build.conf and no arguments given." >&2
  echo "    Binary Ninja is licensed software, so its location cannot be checked in." >&2
  echo "    Do one of:" >&2
  echo "      cp $HERE/build.conf.example $HERE/build.conf   # then edit it" >&2
  echo "      $0 <binaryninja-dir-or-zip> <license.dat>" >&2
  exit 1
fi

BINJA="${1:-$(conf 'binja dir')}"
LICENSE="${2:-$(conf 'license path')}"

# Validate before staging: a wrong path here otherwise surfaces as a confusing
# `cp` failure halfway through building a multi-GB context.
[[ -n "$BINJA"   && -e "$BINJA"   ]] || { echo "[x] Binary Ninja install not found: '${BINJA:-<empty>}' (set 'binja dir' in $HERE/build.conf or pass as arg 1)" >&2; exit 1; }
[[ -n "$LICENSE" && -f "$LICENSE" ]] || { echo "[x] license.dat not found: '${LICENSE:-<empty>}' (set 'license path' in $HERE/build.conf or pass as arg 2)" >&2; exit 1; }

# Keep the (large) staging context off the small root filesystem.
export TMPDIR="${TMPDIR:-$REPO_ROOT/.xbin_scratch}"
mkdir -p "$TMPDIR"
CTX="$(mktemp -d -t binja-plugin-build-XXXXXX)"
trap 'rm -rf "$CTX"' EXIT

echo "[+] Staging build context at $CTX"
# Hardlink the Binary Ninja tree when possible (same filesystem); copy otherwise.
if [[ "$BINJA" == *.zip ]]; then
  echo "[+] Unzipping Binary Ninja..."
  unzip -q "$BINJA" -d "$CTX"
  [[ -d "$CTX/binaryninja" ]] || { echo "[x] Expected 'binaryninja/' at the top level of the zip" >&2; exit 1; }
else
  cp -al "$BINJA" "$CTX/binaryninja" 2>/dev/null || cp -r "$BINJA" "$CTX/binaryninja"
fi
cp "$LICENSE" "$CTX/license.dat"

# The xbin SDK. The orchestrator injects this automatically for plugins it
# builds itself; a prebuilt plugin has to stage it by hand.
cp -r "$REPO_ROOT/src" "$CTX/src"

# pysyndy's Binary Ninja helpers, via the sanctioned xbin_api seam. Prefer the
# in-repo submodule; fall back to a checkout sitting beside the repo (the old
# layout) so an existing dev box keeps working.
PYSYNDY=""
for cand in "$REPO_ROOT/submodules/pysyndy" "$REPO_ROOT/../pysyndy"; do
  [[ -f "$cand/xbin_api.py" ]] && { PYSYNDY="$cand"; break; }
done
if [[ -n "$PYSYNDY" ]]; then
  echo "[+] Using pysyndy from $PYSYNDY"
  cp "$PYSYNDY/xbin_api.py" "$CTX/xbin_api.py"
  cp -r "$PYSYNDY/binja_scripts" "$CTX/binja_scripts"
else
  echo "[!] No pysyndy checkout found (looked in submodules/pysyndy and ../pysyndy)." >&2
  echo "    Run: git submodule update --init submodules/pysyndy" >&2
  echo "    Staging empty stubs so the image still builds; boundary discovery will be degraded." >&2
  : > "$CTX/xbin_api.py"
  mkdir -p "$CTX/binja_scripts"
fi

cp "$HERE/binja_boundary_worker.py" "$HERE/Dockerfile" "$CTX/"

docker build ${NO_CACHE:+--no-cache} -t "$TAG" "$CTX"
echo "[+] built $TAG"
echo "    The orchestrator will now reuse this image (it never rebuilds a .xbin-prebuilt plugin)."
