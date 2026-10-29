#!/usr/bin/env bash
# Package a deliverable archive (source + scripts + docs; no secrets / no wiki HTML).
# Default: tar.gz (zip以外). Also: tar.xz, tar, zip
#   bash scripts/make_archive.sh
#   FORMAT=tar.xz bash scripts/make_archive.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${1:-/opt/cursor/artifacts}"
FORMAT="${FORMAT:-tar.gz}"
mkdir -p "$OUT_DIR" "$ROOT/dist"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
case "$FORMAT" in
  zip)        EXT="zip" ;;
  tar.gz|tgz) EXT="tar.gz"; TAR_FLAGS=(-czf) ;;
  tar.xz|txz) EXT="tar.xz"; TAR_FLAGS=(-cJf) ;;
  tar)        EXT="tar";    TAR_FLAGS=(-cf) ;;
  *)
    echo "unsupported FORMAT=$FORMAT (use zip, tar.gz, tar.xz, or tar)" >&2
    exit 2
    ;;
esac
NAME="bitbank-btc-jpy-bot-${STAMP}.${EXT}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
DEST="$TMP/bitbank-btc-jpy-bot"
mkdir -p "$DEST"

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
  if [[ "$EXT" == "zip" ]]; then
    zip -qr "$OUT_DIR/$NAME" bitbank-btc-jpy-bot
  else
    tar "${TAR_FLAGS[@]}" "$OUT_DIR/$NAME" bitbank-btc-jpy-bot
  fi
  cp -f "$OUT_DIR/$NAME" "$ROOT/dist/$NAME"
)
echo "$OUT_DIR/$NAME"
ls -la "$OUT_DIR/$NAME"
