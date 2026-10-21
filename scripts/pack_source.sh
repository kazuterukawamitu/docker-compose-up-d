#!/usr/bin/env bash
# Pack this bot into a tar.gz for manual copy. Does not SSH and does not use git.
# A failed VPS password is not a successful deploy. This script only builds the archive.

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="${1:-$ROOT/dist/bitbank_source_${STAMP}.tar.gz}"
mkdir -p "$(dirname "$OUT")"

tar \
  --exclude='.env' \
  --exclude='*.pem' \
  --exclude='*.key' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='.venv' \
  --exclude='venv' \
  --exclude='node_modules' \
  --exclude='*.log' \
  --exclude='*.sqlite' \
  --exclude='*.sqlite-*' \
  --exclude='*.db' \
  --exclude='.git' \
  -czf "$OUT" \
  run.sh start.sh run.py main.py requirements.txt pyproject.toml .env.example \
  src tests scripts deploy docs README.md

tar -tzf "$OUT" >/dev/null
echo "収集成功: $OUT"
echo "このアーカイブは手元のファイルです。VPS への転送は別手順です。"
echo "パスワードが拒否された転送では、VPS には何も入っていません。"
