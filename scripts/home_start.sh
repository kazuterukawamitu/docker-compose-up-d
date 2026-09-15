#!/usr/bin/env bash
# Home-safe launcher. Finds the Bitbank clone and execs the real start.sh.
#
# This IS a program-triggered program: when a clone is found it starts the bot.
# It never enables LIVE. It never runs pytest.
#
# Install from the repo:
#   bash scripts/install_launch_alias.sh
# That writes $HOME/start.sh as a wrapper with the clone path baked in.
# This file is the portable finder used when BITBANK_REPO is unset.

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

BOT_BRANCH="cursor/closed-loop-launcher-563e"

not_in_repo() {
  echo "cd to the repo first, then run: bash ./start.sh" >&2
  echo "Typical Mac path (clone name docker-compose-up-d):" >&2
  echo "  cd ~/docker-compose-up-d" >&2
  echo "  git fetch origin $BOT_BRANCH" >&2
  echo "  git checkout $BOT_BRANCH" >&2
  echo "  git ls-files start.sh    # must print: start.sh" >&2
  echo "  bash ./start.sh" >&2
  echo "Or from ~: bash ~/docker-compose-up-d/start.sh" >&2
  echo "If start.sh is missing, you are on main (or not in the clone)." >&2
  echo "Checkout $BOT_BRANCH or merge the PR; do not run tests from ~." >&2
  echo "pytest is not a launch step. Do not paste test commands at ~." >&2
  echo "Do not paste pytest output (.... [ 40%] / 179 passed) into the terminal." >&2
}

looks_like_repo() {
  local d="$1"
  [[ -f "$d/start.sh" && -f "$d/src/bitbank_bot/launch.py" && -f "$d/run.py" && -f "$d/main.py" ]]
}

launch_repo() {
  local p="$1"
  echo "launching Bitbank bot from $p" >&2
  echo "HOLD/WAIT is normal. Paper fills only unless LIVE dual-auth is set." >&2
  exec bash "$p/start.sh" "$@"
}

for a in "$@"; do
  if [[ "$a" =~ ^\.+$ ]] || [[ "$a" =~ ^\[[[:space:]]*[0-9]+%\]$ ]] || [[ "$a" == "passed" || "$a" == "failed" ]]; then
    echo "That looks like pytest output pasted into the shell, not a launcher command." >&2
    not_in_repo
    exit 2
  fi
done

if [[ -n "${BITBANK_REPO:-}" ]] && looks_like_repo "$BITBANK_REPO"; then
  launch_repo "$BITBANK_REPO" "$@"
fi

names="docker-compose-up-d docker-compose-up-d.git bitbank-bot"

if [[ -n "${HOME:-}" ]]; then
  if looks_like_repo "$HOME/docker-compose-up-d"; then
    echo "Found a clone at: $HOME/docker-compose-up-d" >&2
    launch_repo "$HOME/docker-compose-up-d" "$@"
  fi
  for b in "$HOME" "$HOME/src" "$HOME/code" "$HOME/dev" "$HOME/Projects" "$HOME/github" "$HOME/repos"; do
    if looks_like_repo "$b"; then
      echo "Found a clone at: $b" >&2
      launch_repo "$b" "$@"
    fi
    for n in $names; do
      p="$b/$n"
      if looks_like_repo "$p"; then
        echo "Found a clone at: $p" >&2
        launch_repo "$p" "$@"
      fi
    done
  done
fi

echo "No clone named docker-compose-up-d was found under \$HOME." >&2
not_in_repo
exit 2
