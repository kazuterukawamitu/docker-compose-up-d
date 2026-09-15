#!/usr/bin/env bash
# Home-safe start.sh finder. Copy to $HOME/start.sh so that
#   cd ~ && bash ./start.sh
# prints "cd to the repo" instead of bash's raw
#   bash: ./start.sh: No such file or directory
#
# This file is NOT the bot. It never starts trading. It never runs pytest.
# You MUST cd into the clone (common name: docker-compose-up-d).
# Branch: cursor/bitbank-closed-loop-f964
#
# Do not paste this chat, JSON logs, agent reports, or script source.
# Ctrl-C if you see '>'. Then run ONE of:
#   bash ~/docker-compose-up-d/run_transaction.sh
#   bash ~/docker-compose-up-d/start.sh
# Never bash /workspace/start.sh on a Mac. Uses repo .venv, never ~/.venv.
#
# Install from the repo:
#   bash scripts/install_launch_alias.sh

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

BOT_BRANCH="cursor/bitbank-closed-loop-f964"

not_in_repo() {
  echo "cd to the repo first, then run: bash ./start.sh" >&2
  echo "This copy is only a finder. The real start.sh lives inside the clone." >&2
  echo "Do not paste this chat, JSON logs, agent reports, or script source. Ctrl-C if you see '>'. Then run ONE of:" >&2
  echo "  bash ~/docker-compose-up-d/run_transaction.sh" >&2
  echo "  bash ~/docker-compose-up-d/start.sh" >&2
  echo "Never bash /workspace/start.sh on a Mac. Uses repo .venv, never ~/.venv." >&2
  echo "Typical Mac path (clone name docker-compose-up-d):" >&2
  echo "  cd ~/docker-compose-up-d" >&2
  echo "  git fetch origin $BOT_BRANCH" >&2
  echo "  git checkout $BOT_BRANCH" >&2
  echo "  git ls-files start.sh    # must print: start.sh" >&2
  echo "  bash ./run_transaction.sh" >&2
  echo "  bash ./start.sh" >&2
  echo "If start.sh is missing, you are on main (or not in the clone)." >&2
  echo "Checkout $BOT_BRANCH or merge the PR; do not run tests from ~." >&2
  echo "pytest is not a launch step. Do not paste test commands at ~." >&2
  echo "Do not paste pytest output (.... [ 40%] / 179 passed) into the terminal." >&2
}

looks_like_repo() {
  local d="$1"
  [[ -f "$d/start.sh" && -f "$d/src/bitbank_bot/launch.py" && -f "$d/run.py" && -f "$d/main.py" ]]
}

for a in "$@"; do
  if [[ "$a" =~ ^\.+$ ]] || [[ "$a" =~ ^\[[[:space:]]*[0-9]+%\]$ ]] || [[ "$a" == "passed" || "$a" == "failed" ]]; then
    echo "That looks like pytest output pasted into the shell, not a launcher command." >&2
    not_in_repo
    exit 2
  fi
done

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  not_in_repo
  echo "After you cd to the repo, bash ./start.sh --help shows launcher flags." >&2
  exit 2
fi

found=0
names="docker-compose-up-d docker-compose-up-d.git bitbank-bot"
report_clone() {
  local p="$1"
  echo "Found a clone at: $p" >&2
  echo "  cd $p && bash ./start.sh" >&2
  found=1
}

if [[ -n "${BITBANK_REPO:-}" ]] && looks_like_repo "$BITBANK_REPO"; then
  report_clone "$BITBANK_REPO"
fi

if [[ -n "${HOME:-}" ]]; then
  for b in "$HOME" "$HOME/src" "$HOME/code" "$HOME/dev" "$HOME/Projects" "$HOME/github" "$HOME/repos"; do
    if looks_like_repo "$b"; then
      report_clone "$b"
    fi
    for n in $names; do
      p="$b/$n"
      if looks_like_repo "$p"; then
        report_clone "$p"
      fi
    done
  done
fi

if [[ "$found" -eq 0 ]]; then
  echo "No clone named docker-compose-up-d was found under \$HOME." >&2
fi
not_in_repo
exit 2
