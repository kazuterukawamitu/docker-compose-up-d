#!/usr/bin/env bash
# Local Bitbank BTC/JPY launcher.
# Does not clone, fetch, checkout, or log in to Git.
# From any directory:
#   bash /path/to/start.sh
#   python3 /path/to/launch.py

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found" >&2
  exit 2
fi

echo "starting from local files in $ROOT"
echo "git login is not required"
exec python3 "$ROOT/launch.py" "$@"
