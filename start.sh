#!/usr/bin/env bash
# Install a local venv (if needed) and start the Bitbank bot from the clone.
# Do not chmod from ~ — that produces:
#   chmod: start.sh: No such file or directory
# Run after cd into the clone, or by path:
#   bash ~/docker-compose-up-d/start.sh --preflight
#   bash ~/docker-compose-up-d/start.sh --once --synthetic --dry-run

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

CLONE_URL="https://github.com/kazuterukawamitu/docker-compose-up-d.git"

usage_clone() {
  echo "start.sh はこのリポジトリのクローン内にあります。ホーム (~) 単体では動きません。" >&2
  echo "chmod: start.sh: No such file or directory のときは、ファイルが無い場所で chmod しています。" >&2
  echo "chmod は不要です。次をそのまま実行してください:" >&2
  echo "  git clone ${CLONE_URL}" >&2
  echo "  cd docker-compose-up-d" >&2
  echo "  bash ./start.sh --preflight" >&2
  echo "  bash ./start.sh --once --synthetic --dry-run" >&2
  echo "すでに clone 済みなら:" >&2
  echo "  cd docker-compose-up-d" >&2
  echo "  bash ./start.sh --preflight" >&2
  echo "ホームからは:" >&2
  echo "  bash \$HOME/docker-compose-up-d/start.sh --preflight" >&2
}

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -f "$ROOT/pyproject.toml" || ! -f "$ROOT/src/bitbank_bot/__init__.py" ]]; then
  echo "bitbank_bot のソースが見つかりません。" >&2
  echo "cwd=$(pwd)" >&2
  echo "start.sh=$ROOT/start.sh" >&2
  usage_clone
  exit 2
fi

if [[ ! -f "$ROOT/requirements.txt" || ! -f "$ROOT/.env.example" ]]; then
  echo "requirements.txt または .env.example がありません。リポジトリのルートで実行してください。" >&2
  usage_clone
  exit 2
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
  echo "Python 3.12 以上が見つかりません。" >&2
  echo "macOS の /usr/bin/python3 (CommandLineTools) は 3.9 のことが多く、このボットでは使えません。" >&2
  echo "  brew install python@3.12" >&2
  echo "  python3.12 --version" >&2
  echo "その後もう一度 bash ./start.sh を実行してください。" >&2
  echo "グローバルの pip は不要です。venv 内の python -m pip を使います。" >&2
  exit 2
fi

echo "launching bitbank_bot from $ROOT with $PYTHON" >&2

VENV_PY=""
if [[ -x "$ROOT/.venv/bin/python" ]] && "$ROOT/.venv/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
  VENV_PY="$ROOT/.venv/bin/python"
else
  echo "creating venv with $PYTHON"
  if "$PYTHON" -m venv "$ROOT/.venv" && [[ -x "$ROOT/.venv/bin/python" ]]; then
    VENV_PY="$ROOT/.venv/bin/python"
  else
    echo "venv を作れませんでした（python3-venv / ensurepip が無い環境）。同じ Python で直接起動します。" >&2
    rm -rf "$ROOT/.venv"
    VENV_PY="$PYTHON"
  fi
fi

"$VENV_PY" -m pip install -U pip setuptools wheel >/dev/null
"$VENV_PY" -m pip install -r "$ROOT/requirements.txt"
"$VENV_PY" -m pip install -e "$ROOT"

if [[ ! -f "$ROOT/.env" ]]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "Created .env from .env.example (DRY_RUN=true). Edit this file before live trading."
fi

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$VENV_PY" -m bitbank_bot "$@"
