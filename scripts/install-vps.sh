#!/usr/bin/env bash
# Install the bot as a VPS-resident systemd service.
# The Mac / iTerm15 / SSH session is monitor-only after this.
# Does not enable live trading. Does not copy API secrets from the Mac.
#
# On the Sakura VPS (Ubuntu LTS), from a clone of this repo:
#   sudo bash scripts/install-vps.sh
# Then:
#   sudo systemctl status bitbank-bot
#   sudo journalctl -u bitbank-bot -f

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${BITBANK_BOT_HOME:-/opt/bitbank-bot}"
UNIT_SRC="$ROOT/deploy/bitbank-bot.service"
UNIT_DST="/etc/systemd/system/bitbank-bot.service"

if [[ ! -f "$ROOT/src/bitbank_bot/__init__.py" ]]; then
  echo "Run this from the repository clone, not from ~." >&2
  exit 2
fi

if [[ ! -f "$UNIT_SRC" ]]; then
  echo "missing $UNIT_SRC" >&2
  exit 2
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Re-running with sudo..." >&2
  exec sudo --preserve-env=BITBANK_BOT_HOME bash "$0" "$@"
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
  echo "Python 3.12+ is required on the VPS." >&2
  exit 2
fi

mkdir -p "$DEST/src" "$DEST/logs" "$DEST/data"
cp -a "$ROOT/src/bitbank_bot" "$DEST/src/"
cp -a "$ROOT/pyproject.toml" "$ROOT/requirements.txt" "$DEST/"
if [[ -f "$ROOT/.env.example" ]]; then
  cp -a "$ROOT/.env.example" "$DEST/.env.example"
fi
if [[ ! -f "$DEST/.env" ]]; then
  cp "$DEST/.env.example" "$DEST/.env"
  echo "Created $DEST/.env with DRY_RUN=true. Edit it on the VPS only."
fi

"$PYTHON" -m venv "$DEST/.venv"
"$DEST/.venv/bin/python" -m pip install -U pip setuptools wheel
"$DEST/.venv/bin/python" -m pip install -r "$DEST/requirements.txt"
"$DEST/.venv/bin/python" -m pip install -e "$DEST"

install -m 0644 "$UNIT_SRC" "$UNIT_DST"
if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload
  systemctl enable bitbank-bot.service
  systemctl restart bitbank-bot.service
  systemctl --no-pager --full status bitbank-bot.service || true
  echo
  echo "Mac / iTerm15 / SSH can disconnect. The bot is systemd-owned."
  echo "  sudo systemctl status bitbank-bot"
  echo "  sudo systemctl restart bitbank-bot"
  echo "  sudo journalctl -u bitbank-bot -f"
else
  echo "systemctl not found. Unit written to $UNIT_DST; enable it on Ubuntu."
fi
