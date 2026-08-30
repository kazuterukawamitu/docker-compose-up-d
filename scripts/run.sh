#!/usr/bin/env bash
# Prefer bash ./start.sh from the clone root (creates venv, copies .env).
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
export PYTHONPATH=src
exec python3 -m bitbank_bot "$@"
