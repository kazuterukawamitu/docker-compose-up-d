#!/usr/bin/env bash
# Program-triggered program that MUST complete one DRY_RUN paper transaction.
#
# This is the success-path launcher. It finds THIS clone via BASH_SOURCE
# (cwd may be ~), starts the real bot stack, drives one BUY through
# OrderExecutor, prints SMOKE_ORDER_OK SIMULATED_FILL, and exits 0.
# It never calls Bitbank POST /user/spot/order.
#
#   bash ./run_transaction.sh
#   bash /absolute/path/to/run_transaction.sh
#   bash ~/docker-compose-up-d/run_transaction.sh
#
# Continuous 取引画面 (HOLD until README MA cross) is still: bash ./start.sh

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

src="${BASH_SOURCE[0]}"
while [[ -L "$src" ]]; do
  dir="$(cd "$(dirname "$src")" && pwd)"
  src="$(readlink "$src")"
  [[ "$src" != /* ]] && src="$dir/$src"
done
ROOT="$(cd "$(dirname "$src")" && pwd)"
cd "$ROOT"

if [[ ! -f "$ROOT/start.sh" || ! -f "$ROOT/launch_bot.py" || ! -f "$ROOT/src/bitbank_bot/launch.py" ]]; then
  echo "cd to the repo first, then run: bash ./run_transaction.sh" >&2
  echo "Typical clone: cd ~/docker-compose-up-d && bash ./run_transaction.sh" >&2
  exit 2
fi

for a in "$@"; do
  if [[ "$a" =~ ^\.+$ ]] || [[ "$a" =~ ^\[[[:space:]]*[0-9]+%\]$ ]] || [[ "$a" == "passed" || "$a" == "failed" ]]; then
    echo "That looks like pytest output pasted into the shell, not a launcher command." >&2
    echo "Run: bash $ROOT/run_transaction.sh" >&2
    exit 2
  fi
done

echo "run_transaction.sh: DRY_RUN paper BUY via start.sh --smoke-order (no Bitbank POST)"
exec bash "$ROOT/start.sh" --smoke-order --no-screen "$@"
