#!/usr/bin/env bash
# Ultra-fast iTerm paste menu for MacBook Air / Sakura workflow.
# Usage: bash scripts/iterm_ultra_paste.sh [dry|patch|agents|sentry|archive|targz|tarxz]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CMD="${1:-dry}"

case "$CMD" in
  dry|run)
    exec python3 "$ROOT/run.py"
    ;;
  patch|depac|once)
    # Patch/depac smoke: synthetic once, no live orders
    export DRY_RUN=true
    export LIVE_TRADING=false
    if [[ -d "$ROOT/src/bitbank_bot" ]] && python3 -c 'import httpx' 2>/dev/null; then
      PYTHONPATH="$ROOT/src" exec python3 -m bitbank_bot --once --synthetic --no-screen
    fi
    exec python3 "$ROOT/run.py" --once --synthetic --no-screen
    ;;
  agents|verify)
    bash "$ROOT/scripts/parallel_agents.sh"
    ;;
  sentry)
    exec bash "$ROOT/scripts/sentry_verify.sh"
    ;;
  archive|targz|tar.gz)
    FORMAT=tar.gz exec bash "$ROOT/scripts/make_archive.sh" "${2:-/opt/cursor/artifacts}"
    ;;
  tarxz|tar.xz)
    FORMAT=tar.xz exec bash "$ROOT/scripts/make_archive.sh" "${2:-/opt/cursor/artifacts}"
    ;;
  *)
    echo "usage: $0 [dry|patch|agents|sentry|archive|tarxz]" >&2
    exit 2
    ;;
esac
