#!/usr/bin/env bash
# Bitbank BTC/JPY launcher. No git command is invoked. No login is required.
#
# From any directory, including ~. Do not run `/run.sh` — that path is the
# filesystem root and is the wrong file.
#
#   bash /path/to/this/repo/run.sh help
#   bash /path/to/this/repo/run.sh check
#   bash /path/to/this/repo/run.sh dry
#   bash /path/to/this/repo/run.sh once
#   bash /path/to/this/repo/run.sh live-ready
#
# On a Mac checkout the path may look like:
#   /Users/kazuterukawamitsu/btc-jpy-trading-bot/iterm13/iterm15-2/iterm13/5841/run.sh dry
# Copy this file into that directory if the old script was lost. The commands
# are the same five words; only the directory that contains run.sh changes.

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
CMD="${1:-help}"

pick_python() {
  local c
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then
      command -v "$c"
      return 0
    fi
  done
  echo "python3 not found" >&2
  return 1
}

PY="$(pick_python)"

have_package() {
  [[ -f "$ROOT/src/bitbank_bot/main.py" && -f "$ROOT/main.py" ]]
}

force_dry_env() {
  export DRY_RUN=true
  export LIVE_TRADING=false
}

run_stdlib_once() {
  force_dry_env
  exec "$PY" "$ROOT/run.py" --once --synthetic --no-screen
}

usage() {
  cat <<EOF
Bitbank BTC/JPY launcher (no git)

This file: $ROOT/run.sh
Call it by that path from any directory. /run.sh is not this file.

  $ROOT/run.sh help        show this text
  $ROOT/run.sh check       compile and load config; no orders
  $ROOT/run.sh dry         continuous DRY_RUN loop; no Bitbank orders
  $ROOT/run.sh once        one DRY_RUN cycle, then exit; no Bitbank orders
  $ROOT/run.sh live-ready  report whether .env would allow live orders; no orders

Live orders stay off unless .env has DRY_RUN=false, LIVE_TRADING=true, and both API keys.
This script never asks for a Git password and never runs git.
EOF
}

case "$CMD" in
  help|-h|--help)
    usage
    ;;
  check)
    "$PY" -m compileall -q "$ROOT/src" "$ROOT/run.py" "$ROOT/main.py"
    if have_package; then
      PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" "$PY" - <<'PY'
from bitbank_bot.config import load_config
cfg = load_config()
print(
    "check ok"
    f" pair={cfg.pair}"
    f" dry_run={cfg.dry_run}"
    f" live_trading={cfg.live_trading}"
    f" may_place_live_orders={cfg.may_place_live_orders}"
)
print("check does not place an order")
PY
    else
      "$PY" -m py_compile "$ROOT/run.py"
      echo "check ok (stdlib run.py only; package missing)"
    fi
    ;;
  once)
    force_dry_env
    if [[ "${RUN_SH_FORCE_STDLIB:-}" == "1" ]] || ! have_package || ! "$PY" -c "import httpx" >/dev/null 2>&1; then
      run_stdlib_once
    fi
    export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
    exec "$PY" "$ROOT/main.py" --once --no-screen --skip-lock
    ;;
  dry)
    force_dry_env
    if [[ "${RUN_SH_FORCE_STDLIB:-}" == "1" ]] || ! have_package || ! "$PY" -c "import httpx" >/dev/null 2>&1; then
      echo "full package deps missing; stdlib DRY_RUN loop (no orders). Ctrl-C to stop."
      exec "$PY" "$ROOT/run.py" --no-screen
    fi
    exec bash "$ROOT/start.sh" --no-screen
    ;;
  live-ready)
    if ! have_package; then
      echo "live-ready: package missing; not placing an order" >&2
      exit 2
    fi
    PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" "$PY" - <<'PY'
from bitbank_bot.config import ConfigError, load_config
try:
    cfg = load_config()
except ConfigError as exc:
    print(f"live-ready: config error: {exc}")
    print("not placing an order")
    raise SystemExit(2)
print(f"dry_run={cfg.dry_run}")
print(f"live_trading={cfg.live_trading}")
print(f"has_keys={cfg.has_keys}")
print(f"may_place_live_orders={cfg.may_place_live_orders}")
print("live-ready does not place an order")
if not cfg.may_place_live_orders:
    print("not ready: set DRY_RUN=false, LIVE_TRADING=true, and both API keys in .env")
    raise SystemExit(2)
PY
    ;;
  *)
    echo "unknown command: $CMD" >&2
    usage >&2
    exit 2
    ;;
esac
