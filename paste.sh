#!/usr/bin/env bash
# One-paste launcher (ultra-fast). Prefers full package; falls back to stdlib run.py.
# Usage: bash paste.sh
# LIVE (keys required): bash scripts/enable_live.sh && bash start.sh --screen
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
if python3 -c 'import bitbank_bot, httpx' 2>/dev/null; then
  exec python3 -m bitbank_bot --screen "$@"
fi
if [[ -d "$ROOT/src/bitbank_bot" ]]; then
  python3 -m pip install -q -r "$ROOT/requirements.txt" || true
  if python3 -c 'import bitbank_bot, httpx' 2>/dev/null; then
    exec python3 -m bitbank_bot --screen "$@"
  fi
fi
echo "httpx missing; starting stdlib DRY_RUN run.py (no live orders)" >&2
exec python3 "$ROOT/run.py" "$@"
