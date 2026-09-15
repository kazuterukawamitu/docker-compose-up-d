#!/usr/bin/env bash
# From ~ after this branch is checked out:
#   bash ~/docker-compose-up-d/scripts/mac_go.sh
#
# First-time checkout (required if closed_loop.py is missing):
#   cd ~/docker-compose-up-d && git fetch origin cursor/bitbank-closed-loop-1114 && git checkout -B cursor/bitbank-closed-loop-1114 origin/cursor/bitbank-closed-loop-1114 && bash ./start.sh --go
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-}:/usr/bin:/bin"
BRANCH="cursor/bitbank-closed-loop-1114"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -d "$HERE/.git" ]]; then
  REPO="$HERE"
else
  REPO="${BITBANK_REPO:-$HOME/docker-compose-up-d}"
fi
if [[ $# -eq 0 ]]; then
  set -- --go
fi
if [[ ! -f "$REPO/closed_loop.py" || ! -f "$REPO/src/bitbank_bot/__init__.py" || ! -f "$REPO/start.sh" ]]; then
  if [[ ! -d "$REPO/.git" ]]; then
    echo "LAUNCH_FAIL clone missing at $REPO" >&2
    echo "cd ~ && git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git docker-compose-up-d" >&2
    echo "Then: cd ~/docker-compose-up-d && git fetch origin $BRANCH && git checkout -B $BRANCH origin/$BRANCH && bash ./start.sh --go" >&2
    exit 2
  fi
  echo "fetching $BRANCH (closed_loop.py missing on this checkout)" >&2
  git -C "$REPO" fetch origin "$BRANCH"
  git -C "$REPO" checkout -B "$BRANCH" "origin/$BRANCH"
fi
exec bash "$REPO/start.sh" "$@"
