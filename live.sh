#!/usr/bin/env bash
# Live Bitbank BTC/JPY launcher — places real orders when .env says so.
#
# Paste this ONE line in iTerm after putting keys in .env:
#   bash -lc 'REPO="$HOME/docker-compose-up-d"; set -euo pipefail; if [ ! -d "$REPO/.git" ]; then git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git "$REPO"; fi; cd "$REPO"; git fetch origin cursor/bitbank-audit-unify-f5fd; git checkout -B cursor/bitbank-audit-unify-f5fd origin/cursor/bitbank-audit-unify-f5fd; exec bash ./live.sh'
#
# This script never falls back to run.py (that file cannot place orders).

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

if [[ ! -f "$ROOT/src/bitbank_bot/__init__.py" || ! -f "$ROOT/main.py" ]]; then
  echo "bot source not found; fetching $BOT_BRANCH" >&2
  git fetch origin "$BOT_BRANCH"
  git checkout -B "$BOT_BRANCH" "origin/$BOT_BRANCH"
fi

if [[ ! -f "$ROOT/.env" ]]; then
  if [[ -f "$ROOT/live.env.example" ]]; then
    cp "$ROOT/live.env.example" "$ROOT/.env"
    echo "wrote $ROOT/.env from live.env.example" >&2
    echo "Edit .env: set BITBANK_API_KEY and BITBANK_API_SECRET, then run live.sh again." >&2
    echo "Do not paste keys into chat." >&2
    exit 2
  fi
  echo "missing .env — copy live.env.example to .env and add API keys" >&2
  exit 2
fi

has_key=0
has_secret=0
dry_run=true
live_trading=false
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

if [[ "$has_key" -ne 1 || "$has_secret" -ne 1 ]]; then
  echo "LIVE refused: BITBANK_API_KEY / BITBANK_API_SECRET are empty in .env" >&2
  exit 2
fi
if [[ "$dry_run" != "false" || "$live_trading" != "true" ]]; then
  echo "LIVE refused: .env must have DRY_RUN=false and LIVE_TRADING=true" >&2
  echo "start.sh / run.py will not place Bitbank orders." >&2
  exit 2
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
VPIP="$VENV/bin/pip"

if [[ ! -x "$VPY" ]]; then
  echo "creating venv at $VENV with $PY"
  "$PY" -m venv "$VENV"
fi
if [[ ! -x "$VPY" ]]; then
  echo "LIVE refused: venv python missing; cannot place orders without the full package" >&2
  exit 2
fi

if ! "$VPY" -c "import dotenv, httpx" >/dev/null 2>&1; then
  echo "installing dependencies (required for live orders)"
  if [[ -x "$VPIP" ]]; then
    "$VPIP" install -q -r "$ROOT/requirements.txt"
  else
    "$VPY" -m pip install -q -r "$ROOT/requirements.txt"
  fi
fi

if ! "$VPY" -c "import dotenv, httpx" >/dev/null 2>&1; then
  echo "LIVE refused: httpx/dotenv missing. pip install -r requirements.txt" >&2
  echo "run.py cannot place orders." >&2
  exit 2
fi

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

echo "starting LIVE Bitbank BTC/JPY (real orders when a README signal fires)"
echo "mode requires DRY_RUN=false + LIVE_TRADING=true + keys. Ctrl-C stops."
echo "HOLD/WAIT is normal. JSON detail is logs/bot.log (secrets are not logged)."

exec "$VPY" "$ROOT/main.py" --require-live --screen "$@"
