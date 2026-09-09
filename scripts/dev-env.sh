#!/usr/bin/env bash
# Create venv, install runtime + dev tools, run compile + pytest.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONUNBUFFERED=1
PY="${PYTHON:-python3}"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  "$PY" -m venv "$ROOT/.venv"
fi
VPY="$ROOT/.venv/bin/python"
"$VPY" -m pip install -q -r "$ROOT/requirements-dev.txt"
export PYTHONPATH="$ROOT/src"
"$VPY" -m compileall -q src main.py diagnostics.py
"$VPY" -m pytest -q
echo "dev-env ok"
