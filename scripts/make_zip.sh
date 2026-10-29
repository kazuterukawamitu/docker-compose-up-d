#!/usr/bin/env bash
# Package a deliverable zip (source + scripts + docs; no secrets / no wiki HTML dump).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${1:-/opt/cursor/artifacts}"
mkdir -p "$OUT_DIR" "$ROOT/dist"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="bitbank-btc-jpy-bot-${STAMP}.zip"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
DEST="$TMP/bitbank-btc-jpy-bot"
mkdir -p "$DEST"
# Copy without rsync (minimal VPS / cloud images).
while IFS= read -r -d '' path; do
  rel="${path#"$ROOT"/}"
  case "$rel" in
    .git|/*|.git/*|.env|data/state.json|data/bot.lock|logs/*|*/__pycache__/*|.pytest_cache/*|dist/*|*.html|.venv/*) continue ;;
  esac
  if [[ -d "$path" ]]; then
    mkdir -p "$DEST/$rel"
  else
    mkdir -p "$DEST/$(dirname "$rel")"
    cp -a "$path" "$DEST/$rel"
  fi
done < <(find "$ROOT" -mindepth 1 \( \
  -path "$ROOT/.git" -o \
  -path "$ROOT/.git/*" -o \
  -path "$ROOT/.venv" -o \
  -path "$ROOT/.venv/*" -o \
  -path "$ROOT/dist" -o \
  -path "$ROOT/dist/*" -o \
  -path "$ROOT/logs" -o \
  -path "$ROOT/logs/*" -o \
  -path "$ROOT/.pytest_cache" -o \
  -path "$ROOT/.pytest_cache/*" -o \
  -name '__pycache__' -o \
  -name '*.html' \
\) -prune -o -print0)

(
  cd "$TMP"
  zip -qr "$OUT_DIR/$NAME" bitbank-btc-jpy-bot
  cp -f "$OUT_DIR/$NAME" "$ROOT/dist/$NAME"
)
echo "$OUT_DIR/$NAME"
ls -la "$OUT_DIR/$NAME"
