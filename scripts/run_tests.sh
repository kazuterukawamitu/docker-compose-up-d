#!/usr/bin/env bash
# Developer tests only. This is NOT how you start the bot.
# Always cds to the repo that contains this script (never uses ~ as src).
#
#   cd <repo> && bash scripts/run_tests.sh
#   bash ./start.sh --self-test
#
# Do not paste this into zsh at ~. Do not paste pytest dots back into the terminal.

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/.." && pwd)"

if [[ ! -f "$root/start.sh" || ! -f "$root/src/bitbank_bot/launch.py" || ! -d "$root/tests" ]]; then
  echo "cd to the repo first, then run: bash scripts/run_tests.sh" >&2
  echo "This is not a launch command. Launch is: cd <repo> && bash ./start.sh" >&2
  echo "Typical clone: cd ~/docker-compose-up-d && bash ./start.sh" >&2
  exit 2
fi

cd "$root"
export PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}"

if ! python3 -c "import pytest" >/dev/null 2>&1; then
  echo "pytest is not installed. From the repo: python3 -m pip install -e '.[dev]'" >&2
  echo "Still not a launch step. The bot is: bash ./start.sh" >&2
  exit 2
fi

exec python3 -m pytest "$@"
