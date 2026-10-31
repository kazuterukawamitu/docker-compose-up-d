#!/usr/bin/env bash
# Sakura VPS deploy helper (run ON the VPS after SSH).
# Usage:
#   bash scripts/vps_deploy.sh
# Optional LIVE (requires keys already in .env):
#   ENABLE_LIVE=1 bash scripts/vps_deploy.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env || true
  echo "Created .env — set BITBANK_API_KEY / BITBANK_API_SECRET before LIVE."
fi

if [[ "${ENABLE_LIVE:-0}" == "1" ]]; then
  bash scripts/enable_live.sh "$ROOT/.env"
fi

mkdir -p data logs
if command -v docker >/dev/null 2>&1; then
  docker compose up -d --build
  docker compose --profile verify up -d --build verify-agent gap-agent || true
  docker compose ps
  echo "Logs: docker compose logs -f bitbank-bot"
else
  echo "docker not found; using systemd/venv fallback path"
  python3 -m pip install -q -r requirements.txt
  if [[ -f deploy/bitbank-bot.service ]]; then
    echo "Install service manually:"
    echo "  sudo cp $ROOT/deploy/bitbank-bot.service /etc/systemd/system/"
    echo "  sudo systemctl daemon-reload && sudo systemctl enable --now bitbank-bot"
  fi
  echo "Or foreground: PYTHONPATH=src python3 -m bitbank_bot --screen"
fi

PYTHONPATH=src python3 scripts/gap_agent.py
PYTHONPATH=src python3 -m bitbank_bot --check-config || true
