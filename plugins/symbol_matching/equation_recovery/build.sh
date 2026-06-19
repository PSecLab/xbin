#!/usr/bin/env bash
# Build the equation_recovery xbin worker image -- base first, then the worker.
#
#  Stage 1 (base):   leverage docker/build_docker.sh (+ docker/Dockerfile) to
#                    produce the pysyndy base (Binary Ninja + QEMU + Ghidra +
#                    the recovery pipeline). That script tags it `pysyndy`
#                    (== pysyndy:latest); we retag only if a different
#                    PYSINDY_BASE was requested.
#  Stage 2 (worker): build THIS dir's Dockerfile FROM that base, layering the
#                    xbin SDK (injected as src/, FLIRT pattern) + worker code.
#
# Usage:
#   ./build.sh <binaryninja-install-dir> <license.dat> [IMAGE_TAG] [PYSINDY_BASE]
#     binaryninja-install-dir  Binja install dir baked into the base
#     license.dat              Binja license used during the base build
#     IMAGE_TAG                worker image tag
#                              (default: xbin-plugin-symbol_matching-equation_recovery,
#                               the exact name the orchestrator runs on start)
#     PYSINDY_BASE             base image tag    (default: pysyndy:latest)
#
# Prereq: docker/Dockerfile COPYs pysyndy/ and qemu/ from its build context;
# docker/build_docker.sh stages those (plus binaryninja/ + license.dat) for you.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# Framework root holds pysyndy/ (base image build) and xbin/ (the SDK) as
# siblings; this plugin sits 4 levels under it (xbin/plugins/<cat>/<name>).
FRAMEWORK_ROOT="$(cd "$HERE/../../../.." && pwd)"
DOCKER_DIR="$FRAMEWORK_ROOT/pysyndy/docker"   # build_docker.sh + base Dockerfile

# Per-user build inputs live in build.conf next to this script (binja dir +
# license path). Fill it in once. CLI args, if passed, override the file;
# anything still missing is prompted for interactively below.
CONF_FILE="$HERE/build.conf"
conf_get() {  # $1=label -> value from a "label: value" line (quotes/space trimmed)
  [ -f "$CONF_FILE" ] || return 0
  sed -n "s/^[[:space:]]*$1[[:space:]]*:[[:space:]]*//p" "$CONF_FILE" \
    | head -n1 \
    | sed -e 's/[[:space:]]*$//' -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/"
}

BINJA_DIR="${1:-$(conf_get 'binja dir')}"
LICENSE="${2:-$(conf_get 'license path')}"
IMAGE_TAG="${3:-xbin-plugin-symbol_matching-equation_recovery}"
PYSINDY_BASE="${4:-pysyndy:latest}"

# Expand a leading ~ in file-provided paths.
BINJA_DIR="${BINJA_DIR/#\~/$HOME}"
LICENSE="${LICENSE/#\~/$HOME}"

# Prompt for a path until it's non-empty and passes the given test (-d dir /
# -f file). Bails out (instead of hanging) when there's no terminal to read
# from -- e.g. invoked non-interactively; then the value must be passed as an arg.
prompt_path() {  # $1=var name  $2=human label  $3=test flag (-d|-f)
  local cur="${!1}" ans
  while [ -z "$cur" ] || ! test "$3" "$cur"; do
    [ -n "$cur" ] && echo "[!] not found: $cur" >&2
    if [ ! -t 0 ]; then
      echo "[!] $2 required but no terminal to prompt -- pass it as an argument." >&2
      exit 1
    fi
    read -e -r -p "Enter $2: " ans
    cur="${ans/#\~/$HOME}"   # expand a leading ~
  done
  printf -v "$1" '%s' "$cur"
}

prompt_path BINJA_DIR "Binary Ninja install dir"      -d
prompt_path LICENSE   "Binary Ninja license.dat path" -f

# --- Stage 1: base image via docker/build_docker.sh --------------------------
# build_docker.sh cp's into and builds from its own CWD, so run it from docker/.
echo "[*] stage 1: building base via docker/build_docker.sh  (binja=$BINJA_DIR)"
( cd "$DOCKER_DIR" && ./build_docker.sh "$BINJA_DIR" "$LICENSE" )
# build_docker.sh tags the base `pysyndy` (== pysyndy:latest); retag only if a
# different base tag was requested.
if [ "$PYSINDY_BASE" != "pysyndy:latest" ] && [ "$PYSINDY_BASE" != "pysyndy" ]; then
  echo "[*] retagging pysyndy -> $PYSINDY_BASE"
  docker tag pysyndy "$PYSINDY_BASE"
fi

# --- Stage 2: worker image, extending the base ------------------------------
# The worker Dockerfile COPYs the SDK (src/) and the plugin files by paths
# relative to the xbin repo ROOT -- exactly like the orchestrator's in-tree
# build. So build stage 2 with the xbin checkout as the context (no SDK staging
# needed: `COPY src` resolves to the real xbin/src). Set NO_CACHE=1 for a fresh
# layer rebuild.
XBIN_ROOT="$FRAMEWORK_ROOT/xbin"
if [ ! -d "$XBIN_ROOT/src" ]; then
  echo "[!] xbin SDK not found at $XBIN_ROOT/src" >&2
  exit 1
fi

echo "[*] stage 2: docker build -t $IMAGE_TAG  (base=$PYSINDY_BASE, context=$XBIN_ROOT)"
docker build ${NO_CACHE:+--no-cache} \
  --build-arg "PYSINDY_BASE=${PYSINDY_BASE}" \
  -f "$HERE/Dockerfile" \
  -t "$IMAGE_TAG" "$XBIN_ROOT"
echo "[+] built $IMAGE_TAG"
cat <<EOF

Self-test the image (no orchestrator needed):
  docker run --rm \\
    -v /host/license.dat:/root/.binaryninja/license.dat:ro \\
    $IMAGE_TAG /project/binaryninja/bnpython3 /app/selftest_in_image.py

Run the worker alongside the xbin orchestrator + redis:
  docker run --rm --network host \\
    -v /host/license.dat:/root/.binaryninja/license.dat:ro \\
    -v /host/binaries:/in:ro \\
    -e XBIN_ORCHESTRATOR=localhost:50051 -e REDIS_HOST=localhost \\
    -e EQREC_FUNC=myfunc \\
    $IMAGE_TAG
EOF
