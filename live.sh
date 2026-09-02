#!/usr/bin/env bash
# Live Bitbank BTC/JPY launcher — always starts a 取引画面.
#
# Paste this ONE line in iTerm after putting keys in .env:
#   bash -lc 'REPO="$HOME/docker-compose-up-d"; set -euo pipefail; if [ ! -d "$REPO/.git" ]; then git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git "$REPO"; fi; cd "$REPO"; git fetch origin cursor/bitbank-audit-unify-f5fd; git checkout -B cursor/bitbank-audit-unify-f5fd origin/cursor/bitbank-audit-unify-f5fd; exec bash ./live.sh'
#
# This script never falls back to run.py (that file cannot place orders).
# Missing venv/httpx/flags no longer exit 2 — stdlib trade.py --live starts instead.

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

BOT_BRANCH="cursor/bitbank-audit-unify-f5fd"

if [[ ! -f "$ROOT/trade.py" ]]; then
  echo "trade.py not found; fetching $BOT_BRANCH" >&2
  git fetch origin "$BOT_BRANCH"
  git checkout -B "$BOT_BRANCH" "origin/$BOT_BRANCH"
fi

if [[ ! -f "$ROOT/.env" && -f "$ROOT/live.env.example" ]]; then
  cp "$ROOT/live.env.example" "$ROOT/.env"
  echo "wrote $ROOT/.env from live.env.example (keys empty until you edit it)" >&2
  echo "Do not paste keys into chat." >&2
fi

has_key=0
has_secret=0
dry_run=true
live_trading=false
if [[ -f "$ROOT/.env" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    case "$line" in
      ""|\#*) continue ;;
    esac
    key="${line%%=*}"
    val="${line#*=}"
    case "$key" in
      BITBANK_API_KEY)
        if [[ -n "$val" ]]; then has_key=1; fi
        ;;
      BITBANK_API_SECRET)
        if [[ -n "$val" ]]; then has_secret=1; fi
        ;;
      DRY_RUN)
        case "$(printf '%s' "$val" | tr '[:upper:]' '[:lower:]')" in
          0|false|no|off) dry_run=false ;;
        esac
        ;;
      LIVE_TRADING)
        case "$(printf '%s' "$val" | tr '[:upper:]' '[:lower:]')" in
          1|true|yes|on) live_trading=true ;;
        esac
        ;;
    esac
  done < "$ROOT/.env"
fi

pick_python() {
  local c
  for c in \
    /opt/homebrew/bin/python3.12 \
    /usr/local/bin/python3.12 \
    python3.12 \
    /opt/homebrew/bin/python3 \
    /usr/local/bin/python3 \
    python3 \
    python
  do
    if command -v "$c" >/dev/null 2>&1; then
      echo "$c"
      return 0
    fi
  done
  echo "python3 not found. On a Mac: brew install python@3.12" >&2
  return 1
}

PY="$(pick_python)"
VENV="$ROOT/.venv"
VPY="$VENV/bin/python"

start_trade() {
  echo "starting Bitbank BTC/JPY 自動売買 (python3 trade.py --live)" >&2
  echo "HOLD/WAIT is normal. Real POST /v1/user/spot/order needs keys in .env." >&2
  echo "Ctrl-C stops." >&2
  exec "$PY" "$ROOT/trade.py" --live "$@"
}

full_ready=0
if [[ -f "$ROOT/src/bitbank_bot/__init__.py" && -f "$ROOT/main.py" && -x "$VPY" ]]; then
  if "$VPY" -c "import dotenv, httpx" >/dev/null 2>&1; then
    full_ready=1
  fi
fi

if [[ "$full_ready" -eq 1 && "$has_key" -eq 1 && "$has_secret" -eq 1 && "$dry_run" == "false" && "$live_trading" == "true" ]]; then
  export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
  echo "starting LIVE Bitbank BTC/JPY via full package (main.py --require-live)"
  echo "HOLD/WAIT is normal. JSON detail is logs/bot.log (secrets are not logged)."
  exec "$VPY" "$ROOT/main.py" --require-live --screen "$@"
fi

if [[ "$has_key" -ne 1 || "$has_secret" -ne 1 ]]; then
  echo "API keys empty — trade.py still starts (LIVE_BLOCKED until .env has keys)" >&2
fi

start_trade "$@"
