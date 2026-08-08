#!/usr/bin/env bash
# One-shot end-to-end run: preflight -> full-stack driver (boots its own
# orchestrator headless). Headless/server-friendly; tees a timestamped log.
#
# Usage: scripts/e2e.sh [<tier>]
# Tiers come from the installed plugins' manifests: scripts/e2e_driver.py --list-tiers
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
TIER="${1:-smoke}"

PY="$REPO_ROOT/.venv/bin/python"
[[ -x "$PY" ]] || { echo "[x] no .venv found. Run: make setup" >&2; exit 1; }

STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_LOG="$REPO_ROOT/e2e_${TIER}_${STAMP}.log"
ORCH_LOG="$REPO_ROOT/orchestrator_${TIER}_${STAMP}.log"

echo "[*] preflight (tier=$TIER)"
# Preflight prints its own remediation per failed check -- including the ones
# contributed by the installed plugins -- so nothing tool-specific is echoed here.
if ! "$HERE/preflight.sh" --tier "$TIER"; then
  echo "[x] preflight failed (see the remediation next to each FAIL above)." >&2
  exit 1
fi

echo "[*] running e2e driver (tier=$TIER); tee -> $RUN_LOG"
"$PY" "$HERE/e2e_driver.py" --tier "$TIER" --orch-log "$ORCH_LOG" 2>&1 | tee "$RUN_LOG"
