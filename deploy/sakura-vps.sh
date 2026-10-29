#!/usr/bin/env bash
# Sakura VPS: install Docker bot (DRY_RUN by default). Never enables LIVE here.
# Usage on the VPS (as deploy user with docker):
#   bash deploy/sakura-vps.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found. Install Docker Engine first." >&2
  exit 2
fi

if [[ ! -f "$ROOT/.env" ]]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "wrote .env from .env.example (DRY_RUN=true, LIVE_TRADING=false)"
fi

mkdir -p "$ROOT/data" "$ROOT/logs"

echo "building and starting bitbank-bot (compose respects .env; LIVE stays off unless you edit .env)"
docker compose up -d --build

echo "status:"
docker compose ps
echo
echo "Next:"
echo "  docker compose logs -f bitbank-bot"
echo "  PYTHONPATH=src python3 -m bitbank_bot --audit   # on host, or use docker/compose.audit.yml"
echo "LIVE requires editing .env: DRY_RUN=false AND LIVE_TRADING=true AND API keys, then:"
echo "  docker compose up -d --force-recreate"
