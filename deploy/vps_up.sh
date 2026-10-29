#!/usr/bin/env bash
# Sakura VPS one-shot: paste this after cloning the branch.
# Keeps DRY_RUN unless .env already enables LIVE.
set -euo pipefail
cd "$(dirname "$0")/.."
cp -n .env.example .env || true
mkdir -p data logs
if command -v docker >/dev/null 2>&1; then
  # Match Dockerfile bot uid so bind mounts are writable even before entrypoint chown.
  if chown -R 10001:10001 data logs 2>/dev/null; then
    :
  else
    chmod -R a+rwX data logs
  fi
  docker compose up -d --build
  docker compose logs --tail=50 bitbank-bot
else
  python3 -m pip install -r requirements.txt
  PYTHONPATH=src python3 -m bitbank_bot
fi
