#!/usr/bin/env bash
# Bitbank BTC/JPY DRY_RUN launcher (continuous loop).
#
# Paste this ONE line in iTerm — not a stack of commands:
#   bash ~/docker-compose-up-d/start.sh
#
# Do not chmod from ~. Do not run python3 main.py with Apple's system
# interpreter; this script uses .venv/bin/python after installing deps.

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -f "$ROOT/src/bitbank_bot/__init__.py" || ! -f "$ROOT/main.py" ]]; then
  echo "bitbank_bot source not found at $ROOT" >&2
  echo "Clone, then paste this ONE line:" >&2
  echo "  git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git && bash ~/docker-compose-up-d/start.sh" >&2
  exit 2
fi

pick_python() {
  local c
  for c in python3.12 python3 python; do
    if command -v "$c" >/dev/null 2>&1; then
      echo "$c"
      return 0
    fi
  done
  echo "python3 not found" >&2
  return 1
}

PY="$(pick_python)"
PY_MAJ="$("$PY" -c 'import sys; print(sys.version_info.major)')"
PY_MIN="$("$PY" -c 'import sys; print(sys.version_info.minor)')"
if [[ "$PY_MAJ" -lt 3 || ( "$PY_MAJ" -eq 3 && "$PY_MIN" -lt 9 ) ]]; then
  echo "Python 3.9+ is required (found $PY $($PY -V 2>&1))." >&2
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
  echo "pip is not available. On Debian: sudo apt install python3-venv python3-pip" >&2
  echo "On a Mac with Homebrew: brew install python@3.12" >&2
  exit 2
}

need_install=0
if ! "$VPY" -c "import dotenv, httpx" >/dev/null 2>&1; then
  need_install=1
fi
if [[ "$need_install" -eq 1 ]]; then
  echo "installing dependencies"
  install_reqs
  "$VPY" -c "import dotenv, httpx" >/dev/null
fi

if [[ ! -f "$ROOT/.env" ]]; then
  if [[ -f "$ROOT/.env.example" ]]; then
    cp "$ROOT/.env.example" "$ROOT/.env"
    echo "wrote $ROOT/.env from .env.example (DRY_RUN=true, keys empty)"
  fi
fi

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

echo "starting Bitbank BTC/JPY DRY_RUN loop (Ctrl-C to stop)"
echo "HOLD/WAIT on a bar is normal — the bot keeps running."
echo "using $VPY"

# Default (no extra args): continuous loop. Do not pass --once here.
exec "$VPY" "$ROOT/main.py" "$@"
