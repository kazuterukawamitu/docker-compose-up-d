#!/usr/bin/env bash
# Flip .env from DRY_RUN to LIVE (dual confirm). Does not place an order.
# Usage (from repo root):
#   bash scripts/enable_live.sh
# Requires BITBANK_API_KEY and BITBANK_API_SECRET already in .env.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${1:-$ROOT/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ -f "$ROOT/.env.example" ]]; then
    cp "$ROOT/.env.example" "$ENV_FILE"
    echo "created $ENV_FILE from .env.example"
  else
    echo "missing $ENV_FILE" >&2
    exit 2
  fi
fi

has_key="$(grep -E '^BITBANK_API_KEY=.+' "$ENV_FILE" | head -1 || true)"
has_secret="$(grep -E '^BITBANK_API_SECRET=.+' "$ENV_FILE" | head -1 || true)"
if [[ -z "$has_key" || -z "$has_secret" ]]; then
  echo "Refusing LIVE: set BITBANK_API_KEY and BITBANK_API_SECRET in $ENV_FILE first." >&2
  echo "Then re-run: bash scripts/enable_live.sh" >&2
  exit 2
fi

tmp="$(mktemp)"
awk '
  BEGIN { dry=0; live=0; mode=0; trading=0 }
  /^DRY_RUN=/ { print "DRY_RUN=false"; dry=1; next }
  /^LIVE_TRADING=/ { print "LIVE_TRADING=true"; live=1; next }
  /^TRADING_MODE=/ { print "TRADING_MODE=LIVE"; trading=1; next }
  /^MODE=/ { print "MODE=LIVE"; mode=1; next }
  { print }
  END {
    if (!dry) print "DRY_RUN=false"
    if (!live) print "LIVE_TRADING=true"
    if (!trading) print "TRADING_MODE=LIVE"
  }
' "$ENV_FILE" > "$tmp"
mv "$tmp" "$ENV_FILE"
chmod 600 "$ENV_FILE" 2>/dev/null || true

echo "Updated $ENV_FILE:"
echo "  DRY_RUN=false"
echo "  LIVE_TRADING=true"
echo "  TRADING_MODE=LIVE"
echo "Verify (no orders):"
echo "  PYTHONPATH=src python3 -m bitbank_bot --check-config"
echo "Start LIVE loop:"
echo "  bash start.sh --screen"
