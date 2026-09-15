#!/usr/bin/env bash
# Program-triggered launcher: cds to THIS clone (BASH_SOURCE) and execs start.sh.
# Works from ~ or any cwd:
#   bash /absolute/path/to/scripts/run_bot.sh
#   bash ./scripts/run_bot.sh
#
# It never dumps pytest. It never places live orders by itself.

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/.." && pwd)"

if [[ ! -f "$root/start.sh" || ! -f "$root/src/bitbank_bot/launch.py" || ! -f "$root/run.py" ]]; then
  echo "cd to the repo first, then run: bash ./start.sh" >&2
  echo "This helper lives at scripts/run_bot.sh inside the repo." >&2
  echo "Typical clone: cd ~/docker-compose-up-d && bash ./start.sh" >&2
  echo "Need branch cursor/closed-loop-launcher-563e (git ls-files start.sh)." >&2
  echo "Do not paste pytest output (.... [ 40%] / 179 passed) into zsh." >&2
  echo "pytest is not a launch step." >&2
  exit 2
fi

for a in "$@"; do
  if [[ "$a" =~ ^\.+$ ]] || [[ "$a" =~ ^\[[[:space:]]*[0-9]+%\]$ ]] || [[ "$a" == "passed" || "$a" == "failed" ]]; then
    echo "That looks like pytest output pasted into the shell, not a launcher command." >&2
    echo "cd to the repo first, then run: bash ./start.sh" >&2
    exit 2
  fi
done

cd "$root"
echo "run_bot.sh: exec $root/start.sh (cwd was not required to already be the repo)"
exec bash "$root/start.sh" "$@"
