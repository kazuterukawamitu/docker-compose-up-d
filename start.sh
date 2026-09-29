#!/bin/bash
# Bitbank BTC/JPY 取引画面. No Git login. No arrays. Safe on macOS bash 3.2.
# bash "$HOME/docker-compose-up-d/start.sh"
set -eu
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
  PY=python3
fi
if [ ! -f "$ROOT/.env" ] && [ -f "$ROOT/.env.example" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
fi
export PYTHONUNBUFFERED=1
if [ -n "${PYTHONPATH:-}" ]; then
  export PYTHONPATH="$ROOT/src:$PYTHONPATH"
else
  export PYTHONPATH="$ROOT/src"
fi
echo LAUNCH_OK
if [ -f "$ROOT/launch.py" ]; then
  exec "$PY" "$ROOT/launch.py" "$@"
fi
exec "$PY" "$ROOT/run.py" "$@"
