#!/usr/bin/env bash

set -euo pipefail
cd "$(dirname "$0")"                    # build.conf + Dockerfile are right here
conf() { sed -n "s/^$1: *//p" build.conf | tr -d '"'; }

if [ "${1:-}" = base ]; then
  BINJA=$(conf 'binja dir'); LICENSE=$(conf 'license path')
  ( cd ../../../../pysyndy/docker && ./build_docker.sh "$BINJA" "$LICENSE" )
fi

docker build ${NO_CACHE:+--no-cache} --build-arg PYSINDY_BASE=pysyndy:latest \
  -f Dockerfile -t xbin-plugin-symbol_matching-morpheus ../../..
echo "[+] built xbin-plugin-symbol_matching-morpheus"
