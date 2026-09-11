#!/usr/bin/env bash
# Tiny helper: refuse to run unless cwd is the Bitbank bot repo.
# The only supported command is:  cd <repo> && bash ./start.sh
#
# You can also run this file after cd:  bash scripts/run_bot.sh
# It never dumps pytest. It never places live orders.

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/.." && pwd)"

if [[ ! -f "$root/start.sh" || ! -f "$root/src/bitbank_bot/launch.py" || ! -f "$root/run.py" ]]; then
  echo "cd to the repo first, then run: bash ./start.sh" >&2
  echo "This helper lives at scripts/run_bot.sh inside the repo." >&2
  echo "Do not paste pytest output (.... [ 40%] / 179 passed) into zsh." >&2
  exit 2
fi

cwd="$(pwd -P)"
if [[ "$cwd" != "$root" && "$cwd" != "$root"/* ]]; then
  echo "cd to the repo first, then run: bash ./start.sh" >&2
  echo "cwd=$cwd repo=$root" >&2
  echo "If zsh shows '>' you are stuck in paste/continuation — press Ctrl-C." >&2
  exit 2
fi

for a in "$@"; do
  if [[ "$a" =~ ^\.+$ ]] || [[ "$a" =~ ^\[[[:space:]]*[0-9]+%\]$ ]] || [[ "$a" == "passed" || "$a" == "failed" ]]; then
    echo "That looks like pytest output pasted into the shell, not a launcher command." >&2
    echo "cd to the repo first, then run: bash ./start.sh" >&2
    exit 2
  fi
done

exec bash "$root/start.sh" "$@"
