#!/usr/bin/env bash
# One-paste launcher (ultra-fast). DRY_RUN 取引画面. No pip.
# Usage: bash paste.sh
# Or paste the curl one-liner from README into iTerm.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$ROOT/run.py" "$@"
