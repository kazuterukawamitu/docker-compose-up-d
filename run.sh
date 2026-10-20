#!/usr/bin/env bash
# Bitbank BTC/JPY launcher.
#
# From any directory (including ~). `/run.sh` is filesystem root and is wrong.
# Call this file by its absolute path. On the MacBook checkout that path is:
# /Users/kazuterukawamitsu/btc-jpy-trading-bot/iterm13/iterm15-2/iterm13/5841/run.sh help
# /Users/kazuterukawamitsu/btc-jpy-trading-bot/iterm13/iterm15-2/iterm13/5841/run.sh check
# /Users/kazuterukawamitsu/btc-jpy-trading-bot/iterm13/iterm15-2/iterm13/5841/run.sh dry
# /Users/kazuterukawamitsu/btc-jpy-trading-bot/iterm13/iterm15-2/iterm13/5841/run.sh once
# /Users/kazuterukawamitsu/btc-jpy-trading-bot/iterm13/iterm15-2/iterm13/5841/run.sh live-ready
#
# On a Sakura VPS the Mac path does not exist. Use the path printed by `help`
# after the files are on the VPS. Do not paste this program into the serial console.

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

MAC_ROOT="/Users/kazuterukawamitsu/btc-jpy-trading-bot/iterm13/iterm15-2/iterm13/5841"

usage() {
  cat <<EOF
From any directory (including ~). \`/run.sh\` is filesystem root and is wrong.

On this machine:
$ROOT/run.sh help
$ROOT/run.sh check
$ROOT/run.sh dry
$ROOT/run.sh once
$ROOT/run.sh live-ready

MacBook Air checkout, only when the files are at that path:
$MAC_ROOT/run.sh help
$MAC_ROOT/run.sh check
$MAC_ROOT/run.sh dry
$MAC_ROOT/run.sh once
$MAC_ROOT/run.sh live-ready

dry and once force DRY_RUN. live-ready runs preflight and does not send an order.
EOF
}

pick_python() {
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    echo "$ROOT/.venv/bin/python"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    echo python3
    return
  fi
  echo "python3 not found" >&2
  exit 2
}

PY="$(pick_python)"

have_package() {
  "$PY" -c 'import httpx, bitbank_bot' >/dev/null 2>&1
}

cmd="${1:-help}"
shift || true

case "$cmd" in
  help|-h|--help)
    usage
    ;;
  check)
    if have_package; then
      exec "$PY" "$ROOT/main.py" --check-config --no-screen
    fi
    echo "full package missing; stdlib compile check" >&2
    "$PY" -m py_compile "$ROOT/run.py" "$ROOT/main.py"
    echo "check ok (stdlib)"
    ;;
  once)
    export DRY_RUN=true
    export LIVE_TRADING=false
    if have_package; then
      exec "$PY" "$ROOT/main.py" --once --dry-run --no-screen "$@"
    fi
    exec "$PY" "$ROOT/run.py" --once --dry-run --no-screen "$@"
    ;;
  dry)
    export DRY_RUN=true
    export LIVE_TRADING=false
    if have_package; then
      exec "$PY" "$ROOT/main.py" --dry-run "$@"
    fi
    exec "$PY" "$ROOT/run.py" --dry-run "$@"
    ;;
  live-ready)
    if have_package; then
      exec "$PY" "$ROOT/main.py" --preflight --no-screen
    fi
    echo "may_place_live_orders=false"
    echo "live-ready: stdlib runner cannot place Bitbank orders"
    ;;
  *)
    echo "unknown command: $cmd" >&2
    usage >&2
    exit 2
    ;;
esac
