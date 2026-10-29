#!/usr/bin/env bash
# One-paste launcher (ultra-fast). DRY_RUN 取引画面. No pip.
# Usage:
#   bash paste.sh
#   bash paste.sh patch    # synthetic once (patch/depac smoke)
#   bash paste.sh agents   # gap + bug + purpose in parallel
#   bash paste.sh sentry   # needs SENTRY_DSN in env
#   bash paste.sh archive  # tar.gz deliverable (zip以外)
# Or paste the curl one-liner from README into iTerm.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
if [[ "${1:-}" != "" && "${1:-}" != --* ]]; then
  exec bash "$ROOT/scripts/iterm_ultra_paste.sh" "$@"
fi
exec python3 "$ROOT/run.py" "$@"
