#!/usr/bin/env bash
# Ultra-fast Mac / iTerm one-paste installer + DRY_RUN screen.
# Paste this whole file, or:
#   curl -fsSL <raw-url-to-this-script> | bash
#
# Does NOT place LIVE orders. For LIVE after keys are in .env:
#   bash scripts/enable_live.sh && bash start.sh --screen
set -euo pipefail
REPO_URL="${REPO_URL:-https://github.com/kazuterukawamitu/docker-compose-up-d.git}"
BRANCH="${BRANCH:-cursor/bitbank-live-complete-d4a7}"
DEST="${DEST:-$HOME/bitbank-bot}"

mkdir -p "$(dirname "$DEST")"
if [[ -d "$DEST/.git" ]]; then
  git -C "$DEST" fetch origin "$BRANCH"
  git -C "$DEST" checkout "$BRANCH"
  git -C "$DEST" pull --ff-only origin "$BRANCH" || true
else
  git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$DEST"
fi
cd "$DEST"
python3 -m pip install -q -r requirements.txt || true
if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env || true
  echo "Created .env from .env.example (still DRY_RUN)."
fi
mkdir -p data logs
echo "Modules present:"
python3 - <<'PY'
from pathlib import Path
root = Path("src/bitbank_bot")
for name in ("config.py", "rest_client.py", "main.py", "watchdog.py", "v31.py", "oos.py"):
    p = root / name
    print(("OK" if p.is_file() else "MISSING"), p)
PY
echo "Starting DRY_RUN 取引画面 (Ctrl-C to stop)..."
exec env PYTHONPATH=src python3 -m bitbank_bot --screen
