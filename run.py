#!/usr/bin/env python3
"""Run the bot from any working directory.

macOS example (replace the path if you cloned somewhere else):

    python3 ~/docker-compose-up-d/run.py --preflight
    python3 ~/docker-compose-up-d/run.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
PACKAGE = SRC / "bitbank_bot" / "__init__.py"

_CLONE = "https://github.com/kazuterukawamitu/docker-compose-up-d.git"
_BRANCH = "cursor/bitbank-btc-jpy-bot-09cf"


def fail(message: str, code: int = 2) -> None:
    sys.stderr.write(message.rstrip() + "\n")
    raise SystemExit(code)


def require_repo() -> None:
    if PACKAGE.is_file() and (ROOT / "pyproject.toml").is_file():
        return
    fail(
        "bitbank_bot のソースが見つかりません。ホーム (~) や main ブランチではなく、"
        "ボット用ブランチを clone したフォルダで実行してください。\n"
        "chmod: start.sh: No such file or directory のときは start.sh が無い場所で chmod しています。\n"
        "chmod は不要です。\n"
        f"  git clone -b {_BRANCH} {_CLONE}\n"
        "  cd docker-compose-up-d\n"
        "  bash ./start.sh --preflight\n"
        "  bash ./start.sh\n"
        f"現在の run.py: {Path(__file__).resolve()}"
    )


def require_python() -> None:
    if sys.version_info >= (3, 12):
        return
    fail(
        "このボットは Python 3.12 以上が必要です。\n"
        f"今の interpreter: {sys.version.split()[0]} ({sys.executable})\n"
        "macOS では CommandLineTools の python3 は 3.9 のことが多いので、次を使ってください:\n"
        "  brew install python@3.12\n"
        "  python3.12 -m venv .venv\n"
        "  source .venv/bin/activate\n"
        "  python -m pip install -r requirements.txt\n"
        "  python -m bitbank_bot --preflight\n"
        "またはリポジトリ直下で bash ./start.sh を実行してください。"
    )


def main() -> int:
    require_repo()
    require_python()
    src = str(SRC)
    if src not in sys.path:
        sys.path.insert(0, src)
    from bitbank_bot.__main__ import main as bot_main

    return bot_main()


if __name__ == "__main__":
    raise SystemExit(main())
