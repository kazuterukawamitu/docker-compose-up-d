#!/usr/bin/env bash
# Start the Bitbank BTC/JPY bot from any directory (including ~).
#
# Paste this ONE line in iTerm2 (zsh is fine; this wraps bash). Do not use !.
#
# bash -lc 'set -euo pipefail; REPO="$HOME/docker-compose-up-d"; if [ ! -d "$REPO/.git" ]; then git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git "$REPO"; fi; cd "$REPO"; if [ ! -f src/bitbank_bot/__init__.py ]; then git fetch origin cursor/closed-loop-runtime-hardening; git checkout -B cursor/closed-loop-runtime-hardening origin/cursor/closed-loop-runtime-hardening; fi; exec bash scripts/iterm-launch.sh --screen'
#
# This script never enables LIVE. It only fetches a branch when the Python
# package is missing (wiki-only main). If src/bitbank_bot already exists,
# it starts immediately and does not switch branches.

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8

HERE="$(cd "$(dirname "$0")" && pwd)"
BOT_BRANCH="cursor/closed-loop-runtime-hardening"
REPO_URL="https://github.com/kazuterukawamitu/docker-compose-up-d.git"

resolve_root() {
  if [[ -f "$HERE/../src/bitbank_bot/__init__.py" || -f "$HERE/../bitbank-bot" || -f "$HERE/../main.py" ]]; then
    cd "$HERE/.." && pwd
    return
  fi
  if [[ -n "${BITBANK_BOT_ROOT:-}" && -d "$BITBANK_BOT_ROOT" ]]; then
    cd "$BITBANK_BOT_ROOT" && pwd
    return
  fi
  if [[ -d "$HOME/docker-compose-up-d" ]]; then
    cd "$HOME/docker-compose-up-d" && pwd
    return
  fi
  echo "$HOME/docker-compose-up-d"
}

ROOT="$(resolve_root)"

if [[ ! -d "$ROOT/.git" ]]; then
  echo "cloning Bitbank bot into $ROOT" >&2
  git clone "$REPO_URL" "$ROOT"
fi

cd "$ROOT"

if [[ ! -f "$ROOT/src/bitbank_bot/__init__.py" || ! -f "$ROOT/main.py" ]]; then
  echo "bot source missing at $ROOT (clone is probably still on main / wiki dump)" >&2
  echo "fetching $BOT_BRANCH so the trading screen can start" >&2
  git fetch origin "$BOT_BRANCH"
  git checkout -B "$BOT_BRANCH" "origin/$BOT_BRANCH"
fi

if [[ ! -f "$ROOT/src/bitbank_bot/__init__.py" || ! -f "$ROOT/main.py" ]]; then
  echo "still no bitbank_bot after checkout; branch may not be fetched" >&2
  exit 2
fi

chmod +x "$ROOT/bitbank-bot" "$ROOT/start.sh" 2>/dev/null || true

if [[ $# -eq 0 ]]; then
  set -- --screen
fi

if [[ -x "$ROOT/bitbank-bot" ]]; then
  echo "starting from $ROOT (not from ~)"
  exec "$ROOT/bitbank-bot" "$@"
fi

if [[ -f "$ROOT/start.sh" ]]; then
  echo "bitbank-bot missing; using start.sh from $ROOT" >&2
  exec bash "$ROOT/start.sh" "$@"
fi
if [[ -f "$ROOT/run.py" ]]; then
  echo "full launcher missing; starting stdlib DRY_RUN (run.py, no orders)" >&2
  exec python3 "$ROOT/run.py" "$@"
fi
echo "no bitbank-bot, start.sh, or run.py at $ROOT" >&2
exit 2
