#!/usr/bin/env bash
# Install a local venv (if needed) and start the Bitbank bot.
# Safe to invoke from any directory, including ~ :
#   ~/docker-compose-up-d/start.sh --preflight
#   ~/docker-compose-up-d/start.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -f "$ROOT/pyproject.toml" || ! -f "$ROOT/src/bitbank_bot/__init__.py" ]]; then
  echo "bitbank_bot のリポジトリ直下で実行してください。" >&2
  echo "  git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git" >&2
  echo "  cd docker-compose-up-d" >&2
  echo "  ./start.sh --preflight" >&2
  exit 2
fi

pick_python() {
  local c
  for c in python3.13 python3.12 python3; do
    if command -v "$c" >/dev/null 2>&1; then
      if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
        printf '%s\n' "$c"
        return 0
      fi
    fi
  done
  return 1
}

if ! PYTHON="$(pick_python)"; then
  echo "Python 3.12 以上が見つかりません。" >&2
  echo "macOS の /usr/bin/python3 (CommandLineTools) は 3.9 のことが多く、このボットでは使えません。" >&2
  echo "  brew install python@3.12" >&2
  echo "  python3.12 --version" >&2
  echo "その後もう一度 ./start.sh を実行してください。" >&2
  exit 2
fi

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "creating venv with $PYTHON"
  "$PYTHON" -m venv "$ROOT/.venv"
fi

VENV_PY="$ROOT/.venv/bin/python"
"$VENV_PY" -m pip install -U pip setuptools wheel >/dev/null
"$VENV_PY" -m pip install -r "$ROOT/requirements.txt"
"$VENV_PY" -m pip install -e "$ROOT"

if [[ ! -f "$ROOT/.env" ]]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "Created .env from .env.example (DRY_RUN=true). Edit this file before live trading."
fi

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$VENV_PY" "$ROOT/run.py" "$@"
