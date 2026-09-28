#!/usr/bin/env bash
# Local Bitbank BTC/JPY launcher.
# Does not clone, fetch, checkout, pull, or log in to Git.
#
#   bash ./start.sh
#   python3 ./launch.py
#
# From iTerm, without a checkout and without a Git login:
#   curl -fsSL -o "$HOME/bitbank_launch.py" https://raw.githubusercontent.com/kazuterukawamitu/docker-compose-up-d/cursor/git-free-launch-fa47/launch.py && python3 "$HOME/bitbank_launch.py"

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8
export GIT_TERMINAL_PROMPT=0

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found" >&2
  exit 2
fi

echo "starting from local files in $ROOT"
echo "git login is not required"
exec python3 "$ROOT/launch.py" "$@"
