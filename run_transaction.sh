#!/usr/bin/env bash
# One-shot DRY_RUN paper transaction. Not the 取引画面 loop. Does not POST live orders.
# cds to this repo via BASH_SOURCE, uses $ROOT/.venv/bin/python only (via start.sh).
#
# From ~ on a Mac, copy-paste ONLY this ONE line (do not paste this chat):
#   bash ~/docker-compose-up-d/run_transaction.sh
# If the clone exists but may be on the wrong branch:
#   bash -lc 'cd "$HOME/docker-compose-up-d" && git fetch origin cursor/bitbank-closed-loop-f964 && git checkout cursor/bitbank-closed-loop-f964 && exec bash ./run_transaction.sh'
#
# Continuous 取引画面 (HOLD/WAIT is normal; that is NOT a failed transaction):
#   bash ~/docker-compose-up-d/start.sh
#
# Never bash /workspace/start.sh on a Mac. Never ~/.venv.
if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi
set -euo pipefail
set +H 2>/dev/null || true
set +o histexpand 2>/dev/null || true

src="${BASH_SOURCE[0]}"
while [[ -L "$src" ]]; do
  dir="$(cd "$(dirname "$src")" && pwd)"
  src="$(readlink "$src")"
  [[ "$src" != /* ]] && src="$dir/$src"
done
ROOT="$(cd "$(dirname "$src")" && pwd)"
cd "$ROOT"

BOT_BRANCH="cursor/bitbank-closed-loop-f964"
if [[ -d "$ROOT/.git" ]]; then
  current="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  if [[ -n "$current" && "$current" != "$BOT_BRANCH" && "$current" != "HEAD" ]]; then
    echo "checking out $BOT_BRANCH (was ${current:-unknown})" >&2
    git fetch origin "$BOT_BRANCH"
    git checkout -B "$BOT_BRANCH" "origin/$BOT_BRANCH"
  fi
fi

# Paper path only. Existing env/.env LIVE flags must not POST.
export DRY_RUN=true
export LIVE_TRADING=false
export TRADING_MODE=DRY_RUN
export ENABLE_WEBSOCKET=false

echo "paper DRY_RUN transaction (no Bitbank POST). Success: SMOKE_ORDER_OK / SIMULATED_FILL"
echo "HOLD is the continuous screen: bash ~/docker-compose-up-d/start.sh"
exec bash "$ROOT/start.sh" --execute --smoke-order --skip-lock --no-screen "$@"
