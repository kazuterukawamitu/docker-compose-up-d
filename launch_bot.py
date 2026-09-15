"""Repo-root entry so `python launch_bot.py` works. Not a second bot.

Inserts src/ on sys.path from this file's location, then calls
bitbank_bot.launch.main. Prefer `bash start.sh`, which uses
$ROOT/.venv/bin/python only (never ~/.venv).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _refuse_home_venv() -> None:
    home_venv = Path.home() / ".venv"
    if not home_venv.exists():
        return
    try:
        Path(sys.executable).resolve().relative_to(home_venv.resolve())
    except (ValueError, OSError):
        return
    repo_venv = (ROOT / ".venv").resolve()
    try:
        Path(sys.executable).resolve().relative_to(repo_venv)
        return
    except (ValueError, OSError):
        pass
    sys.stderr.write(
        "refusing ~/.venv. Use bash ~/docker-compose-up-d/start.sh "
        "(that uses the repo .venv only).\n"
    )
    raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    _refuse_home_venv()
    from bitbank_bot.launch import main as launch_main

    return int(launch_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
