#!/usr/bin/env bash
# Start the Bitbank bot from the clone. Do not chmod this from ~.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -f "$ROOT/src/bitbank_bot/__init__.py" ]]; then
  echo "bitbank_bot source not found. Run from the repository clone." >&2
  echo "  git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git" >&2
  echo "  cd docker-compose-up-d" >&2
  echo "  bash ./start.sh --once --synthetic --dry-run --skip-lock" >&2
  exit 2
fi

pick_python() {
  local c
  for c in python3.12 python3; do
    if command -v "$c" >/dev/null 2>&1; then
      echo "$c"
      return
    fi
  done
  echo "python3" >&2
  return 1
}

PY="$(pick_python)"
if ! "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
  echo "Python 3.12+ is required." >&2
  exit 2
fi

if [[ ! -d "$ROOT/.venv" ]]; then
  "$PY" -m venv "$ROOT/.venv"
  "$ROOT/.venv/bin/pip" install -q -r "$ROOT/requirements.txt"
fi

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$ROOT/.venv/bin/python" "$ROOT/main.py" "$@"
