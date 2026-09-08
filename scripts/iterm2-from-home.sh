#!/usr/bin/env bash
# Start the Bitbank bot from any directory, including macOS home (~).
#
# iTerm2 often opens in ~. `python3 main.py` then looks for ~/main.py and fails:
#   can't open file '/Users/<you>/main.py': [Errno 2] No such file or directory
#
# Paste ONE of these in iTerm (zsh is fine):
#
# First time (clone if needed, then open the DRY_RUN 取引画面):
#   bash -lc 'REPO="$HOME/docker-compose-up-d"; set -euo pipefail; if [ ! -d "$REPO/.git" ]; then git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git "$REPO"; fi; cd "$REPO"; git fetch origin cursor/bitbank-closed-loop-execution-dee2; git checkout -B cursor/bitbank-closed-loop-execution-dee2 origin/cursor/bitbank-closed-loop-execution-dee2; exec bash ./scripts/iterm2-from-home.sh'
#
# Already cloned at ~/docker-compose-up-d:
#   bash "$HOME/docker-compose-up-d/scripts/iterm2-from-home.sh"
#
# One-cycle smoke test (exits on purpose; does not keep the dashboard open):
#   bash "$HOME/docker-compose-up-d/scripts/iterm2-from-home.sh" --once --skip-lock --no-screen
#
# Do not run: python3 main.py   from ~.

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

REPO_URL="https://github.com/kazuterukawamitu/docker-compose-up-d.git"
BOT_BRANCH="${BITBANK_BRANCH:-cursor/bitbank-closed-loop-execution-dee2}"
DEFAULT_REPO="${BITBANK_REPO:-$HOME/docker-compose-up-d}"

script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_from_script="$(cd "$script_dir/.." && pwd)"

if [[ -f "$repo_from_script/main.py" && -f "$repo_from_script/start.sh" ]]; then
  REPO="$repo_from_script"
elif [[ -f "$DEFAULT_REPO/main.py" && -f "$DEFAULT_REPO/start.sh" ]]; then
  REPO="$DEFAULT_REPO"
else
  REPO="$DEFAULT_REPO"
  if [[ ! -d "$REPO/.git" ]]; then
    echo "cloning $REPO_URL into $REPO" >&2
    git clone "$REPO_URL" "$REPO"
  fi
fi

cd "$REPO"

if [[ ! -f "$REPO/main.py" || ! -f "$REPO/start.sh" ]]; then
  echo "bot files missing in $REPO; fetching $BOT_BRANCH" >&2
  git fetch origin "$BOT_BRANCH"
  git checkout -B "$BOT_BRANCH" "origin/$BOT_BRANCH"
fi

if [[ ! -f "$REPO/main.py" ]]; then
  echo "still no main.py in $REPO" >&2
  echo "cd into the folder that contains main.py, then run: bash ./start.sh --screen" >&2
  exit 2
fi

if [[ $# -eq 0 ]]; then
  exec bash "$REPO/start.sh" --screen
fi

exec bash "$REPO/start.sh" "$@"
