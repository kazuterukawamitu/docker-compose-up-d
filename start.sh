#!/usr/bin/env bash
# Bitbank BTC/JPY launcher. This script cds to its own directory.
#
# From ~ on the Mac (zsh is fine), paste this ONE line — replace nothing:
#   cd ~/docker-compose-up-d && git fetch origin cursor/bitbank-closed-loop-1114 && git checkout -B cursor/bitbank-closed-loop-1114 origin/cursor/bitbank-closed-loop-1114 && bash ./start.sh --go
#
# Do not run python3 closed_loop.py or python3 main.py from ~.
# Do not run bash ./start.sh from ~ (that is a home finder, not this file).
# Do not type /path/to/... literally. Do not paste pytest at ~.

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-}:/usr/bin:/bin"
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

BOT_BRANCH="cursor/bitbank-closed-loop-1114"

for _arg in "$@"; do
  if [[ "$_arg" == "--help" || "$_arg" == "-h" ]]; then
    cat <<EOF
LAUNCH_OK  Bitbank BTC/JPY launcher

Do not run python3 closed_loop.py or python3 main.py from ~ (home).
That looks for ~/closed_loop.py (missing) or runs ~/main.py (Sentry BadDsn).
Do not run bash ./start.sh from ~ — that is a home finder for another branch.
Do not type /path/to/... literally.

From ~ on this Mac, paste this ONE line (replace nothing):

  cd ~/docker-compose-up-d && git fetch origin ${BOT_BRANCH} && git checkout -B ${BOT_BRANCH} origin/${BOT_BRANCH} && bash ./start.sh --go

Later starts:

  bash ~/docker-compose-up-d/start.sh --go

Continuous 取引画面:

  bash ~/docker-compose-up-d/start.sh --screen

This file's repo is: $ROOT
EOF
    exit 0
  fi
done

ensure_bot_source() {
  if [[ -f "$ROOT/src/bitbank_bot/__init__.py" && -f "$ROOT/main.py" && -f "$ROOT/closed_loop.py" ]]; then
    return 0
  fi
  echo "bot source not found at $ROOT (clone is on main, wiki dump, or another launcher branch)" >&2
  if [[ ! -d "$ROOT/.git" ]]; then
    echo "Paste this ONE line at the ~ prompt:" >&2
    echo "  git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git \"\$HOME/docker-compose-up-d\" && cd \"\$HOME/docker-compose-up-d\" && git fetch origin $BOT_BRANCH && git checkout -B $BOT_BRANCH origin/$BOT_BRANCH && bash ./start.sh --go" >&2
    exit 2
  fi
  echo "fetching $BOT_BRANCH so closed_loop.py and the trading screen exist" >&2
  git fetch origin "$BOT_BRANCH"
  git checkout -B "$BOT_BRANCH" "origin/$BOT_BRANCH"
  if [[ ! -f "$ROOT/src/bitbank_bot/__init__.py" || ! -f "$ROOT/main.py" || ! -f "$ROOT/closed_loop.py" ]]; then
    echo "still no closed_loop.py after checkout; paste:" >&2
    echo "  cd ~/docker-compose-up-d && git fetch origin $BOT_BRANCH && git checkout -B $BOT_BRANCH origin/$BOT_BRANCH && bash ./start.sh --go" >&2
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

if ! "$VPY" -c "import dotenv, httpx" >/dev/null 2>&1; then
  echo "pip packages missing; starting stdlib DRY_RUN (python3 run.py, no orders)"
  exec "$PY" "$ROOT/run.py"
fi

if [[ ! -f "$ROOT/.env" ]]; then
  if [[ -f "$ROOT/.env.example" ]]; then
    cp "$ROOT/.env.example" "$ROOT/.env"
    echo "wrote $ROOT/.env from .env.example (DRY_RUN=true, keys empty)"
  fi
fi

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

want_screen=0
if [[ -t 1 ]]; then
  want_screen=1
fi
for a in "$@"; do
  case "$a" in
    --once|--check-config|--preflight|--backtest|--no-screen|--go)
      want_screen=0
      ;;
    --screen)
      want_screen=1
      ;;
  esac
done

SCREEN_ARGS=()
if [[ "$want_screen" -eq 1 && ! -t 1 ]]; then
  echo "LAUNCH_OK stdout is not a TTY; printing JSON instead of 取引画面"
  FILTERED=()
  for a in "$@"; do
    if [[ "$a" != "--screen" ]]; then
      FILTERED+=("$a")
    fi
  done
  set -- "${FILTERED[@]}"
  SCREEN_ARGS=(--no-screen)
  want_screen=0
fi
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

echo "HOLD/WAIT is normal. JSON detail is logs/bot.log"
echo "using $VPY"

for _arg in "$@"; do
  if [[ "$_arg" == "--go" ]]; then
    echo "LAUNCH_OK  bash start.sh --go"
    exec "$VPY" "$ROOT/closed_loop.py" --go
  fi
done

if [[ "$want_screen" -eq 1 ]]; then
  echo "LAUNCH_OK opening Bitbank BTC/JPY 取引画面 (Ctrl-C to stop)"
else
  echo "LAUNCH_OK starting Bitbank BTC/JPY JSON DRY_RUN (Ctrl-C to stop)"
fi

# Default (no extra args): continuous loop + trading screen on a TTY.
# Do not pass --once here.
exec "$VPY" "$ROOT/main.py" "${SCREEN_ARGS[@]}" "$@"
