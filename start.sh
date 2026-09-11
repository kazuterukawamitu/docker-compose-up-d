#!/usr/bin/env bash
# Enhanced Bitbank BTC/JPY launcher (Mac iTerm + Sakura VPS).
#
# Paste this ONE line in iTerm (zsh is fine; this wraps bash):
#   bash -lc 'REPO="$HOME/docker-compose-up-d"; set -euo pipefail; if [ ! -d "$REPO/.git" ]; then git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git "$REPO"; fi; cd "$REPO"; git fetch origin cursor/bitbank-closed-loop-f964; git checkout -B cursor/bitbank-closed-loop-f964 origin/cursor/bitbank-closed-loop-f964; exec bash ./start.sh --screen'
#
# Locates this repo (no hardcoded /Users/... path), creates .venv if needed,
# loads .env without printing secrets, then starts the existing bot entrypoint.
# Do not paste python3 main.py. Do not use history-expansion bangs.

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8

usage() {
  cat <<'EOF'
Usage: bash ./start.sh [options]

Enhanced launcher for the existing Bitbank BTC/JPY bot (DRY_RUN by default).

  bash ./start.sh
  bash ./start.sh --once --synthetic --skip-lock --no-screen
  bash ./start.sh --check-config
  bash ./start.sh --no-supervise
  bash ./start.sh --supervise

Locates the repo from this script (not a hardcoded Mac path), uses .venv,
loads .env without printing secrets, prints SET/UNSET diagnostics, and
restarts on crash with backoff (not on config/lock failures). systemd
already restarts: pass --no-supervise (or run python -m bitbank_bot).

LIVE requires TRADING_MODE=LIVE and LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK.
JSON logs: logs/bot.log (rotated 5MB x 5). Ctrl-C stops. data/KILL halts new orders.
Other flags pass through to python -m bitbank_bot.
EOF
}

resolve_root() {
  local src="${BASH_SOURCE[0]}"
  while [[ -L "$src" ]]; do
    local dir
    dir="$(cd "$(dirname "$src")" && pwd)"
    src="$(readlink "$src")"
    [[ "$src" != /* ]] && src="$dir/$src"
  done
  cd "$(dirname "$src")" && pwd
}

ROOT="$(resolve_root)"
cd "$ROOT"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

BOT_BRANCH="cursor/bitbank-closed-loop-f964"

ensure_bot_source() {
  if [[ -f "$ROOT/src/bitbank_bot/__init__.py" && -f "$ROOT/main.py" ]]; then
    return 0
  fi
  echo "bot source not found at $ROOT (this clone is probably still on main / wiki dump)" >&2
  if [[ ! -d "$ROOT/.git" ]]; then
    echo "Paste this ONE line in iTerm:" >&2
    echo "  bash -lc 'git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git \"\$HOME/docker-compose-up-d\" && bash \"\$HOME/docker-compose-up-d/start.sh\" --screen'" >&2
    exit 2
  fi
  echo "fetching $BOT_BRANCH so the trading screen can start" >&2
  git fetch origin "$BOT_BRANCH"
  git checkout -B "$BOT_BRANCH" "origin/$BOT_BRANCH"
  if [[ ! -f "$ROOT/src/bitbank_bot/__init__.py" || ! -f "$ROOT/main.py" ]]; then
    echo "still no bitbank_bot after checkout; branch may not be fetched" >&2
    exit 2
  fi
}

ensure_bot_source

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
PY_MAJ="$("$PY" -c 'import sys; print(sys.version_info.major)')"
PY_MIN="$("$PY" -c 'import sys; print(sys.version_info.minor)')"
if [[ "$PY_MAJ" -lt 3 || ( "$PY_MAJ" -eq 3 && "$PY_MIN" -lt 9 ) ]]; then
  echo "Python 3.9+ is required (found $PY $($PY -V 2>&1))." >&2
  echo "On a Mac: brew install python@3.12" >&2
  exit 2
fi
if [[ "$PY_MAJ" -eq 3 && "$PY_MIN" -lt 12 ]]; then
  echo "note: $PY is $($PY -V 2>&1); 3.12 is preferred, continuing with this interpreter." >&2
fi

VENV="$ROOT/.venv"
VPY="$VENV/bin/python"
VPIP="$VENV/bin/pip"

if [[ ! -x "$VPY" ]]; then
  echo "creating venv at $VENV with $PY"
  set +e
  "$PY" -m venv "$VENV"
  venv_rc=$?
  set -e
  if [[ ! -x "$VPY" ]]; then
    set +e
    "$PY" -m venv --without-pip "$VENV"
    set -e
  fi
  if [[ ! -x "$VPY" ]]; then
    echo "venv python missing; using $PY directly" >&2
    VPY="$PY"
    VPIP=""
  elif [[ "$venv_rc" -ne 0 ]]; then
    echo "note: python -m venv reported an error (often missing ensurepip); continuing."
  fi
fi

install_reqs() {
  if [[ -n "${VPIP}" && -x "$VPIP" ]]; then
    "$VPIP" install -q -r "$ROOT/requirements.txt"
    return
  fi
  if "$VPY" -m pip --version >/dev/null 2>&1; then
    "$VPY" -m pip install -q -r "$ROOT/requirements.txt"
    return
  fi
  if "$PY" -m pip --version >/dev/null 2>&1; then
    SITE="$("$VPY" -c 'import sysconfig; print(sysconfig.get_path("purelib"))')"
    mkdir -p "$SITE"
    "$PY" -m pip install -q -r "$ROOT/requirements.txt" --target "$SITE"
    return
  fi
  echo "pip is not available." >&2
  echo "On a Mac with Homebrew: brew install python@3.12" >&2
  echo "On Debian: sudo apt install python3-venv python3-pip" >&2
  exit 2
}

need_install=0
if ! "$VPY" -c "import dotenv, httpx" >/dev/null 2>&1; then
  need_install=1
fi
if [[ "$need_install" -eq 1 ]]; then
  echo "installing dependencies"
  set +e
  install_reqs
  set -e
fi

oneshot=0
want_stdlib_loop=1
for a in "$@"; do
  case "$a" in
    --once|--check-config|--preflight|--backtest|--help|-h|--max-cycles)
      oneshot=1
      want_stdlib_loop=0
      ;;
    --no-supervise)
      want_stdlib_loop=0
      ;;
  esac
done

if ! "$VPY" -c "import dotenv, httpx" >/dev/null 2>&1; then
  echo "pip packages missing; starting stdlib DRY_RUN (python3 run.py, no orders)"
  if [[ "$oneshot" -eq 1 || "$want_stdlib_loop" -eq 0 ]]; then
    exec "$PY" "$ROOT/run.py" "$@"
  fi
  delay=2
  while true; do
    set +e
    "$PY" "$ROOT/run.py" "$@"
    rc=$?
    set -e
    if [[ "$rc" -eq 0 || "$rc" -eq 130 || "$rc" -eq 143 || "$rc" -eq 2 ]]; then
      if [[ "$rc" -eq 2 ]]; then
        echo "stdlib launcher: fatal exit 2 (not restarting)" >&2
      fi
      exit "$rc"
    fi
    echo "stdlib launcher: crash exit $rc; restart in ${delay}s" >&2
    sleep "$delay"
    delay=$((delay * 2))
    if [[ "$delay" -gt 30 ]]; then
      delay=30
    fi
  done
fi

if [[ ! -f "$ROOT/.env" ]]; then
  if [[ -f "$ROOT/.env.example" ]]; then
    cp "$ROOT/.env.example" "$ROOT/.env"
    echo "wrote $ROOT/.env from .env.example (DRY_RUN=true, keys empty; values not printed)"
  fi
fi

mkdir -p "$ROOT/logs" "$ROOT/data"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

want_screen=0
if [[ -t 1 ]]; then
  want_screen=1
fi
for a in "$@"; do
  case "$a" in
    --once|--check-config|--preflight|--backtest|--no-screen)
      want_screen=0
      ;;
    --screen)
      want_screen=1
      ;;
  esac
done

SCREEN_ARGS=()
if [[ "$want_screen" -eq 1 ]]; then
  has_screen=0
  for a in "$@"; do
    if [[ "$a" == "--screen" ]]; then
      has_screen=1
    fi
  done
  if [[ "$has_screen" -eq 0 ]]; then
    SCREEN_ARGS=(--screen)
  fi
fi

SUPERVISE_ARGS=()
if [[ -n "${INVOCATION_ID:-}" ]]; then
  has_sup=0
  for a in "$@"; do
    case "$a" in
      --supervise|--no-supervise) has_sup=1 ;;
    esac
  done
  if [[ "$has_sup" -eq 0 ]]; then
    SUPERVISE_ARGS=(--no-supervise)
  fi
fi

echo "opening Bitbank BTC/JPY 取引画面 (Ctrl-C to stop)"
echo "HOLD/WAIT is normal. JSON detail is logs/bot.log (rotated; do not dump stdout)"
echo "project_root=$ROOT"
echo "using $VPY"
echo "lock=$ROOT/data/bot.lock kill=$ROOT/data/KILL (create KILL to halt new orders)"

# Default (no extra args): continuous loop + trading screen on a TTY.
# Do not pass --once here. Crash backoff lives in bitbank_bot.launch.
exec "$VPY" -m bitbank_bot.launch "${SUPERVISE_ARGS[@]}" "${SCREEN_ARGS[@]}" "$@"
