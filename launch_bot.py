"""Repo-root entry so `python launch_bot.py` works. Not a second bot.

Inserts src/ on sys.path from this file's location, then calls
bitbank_bot.launch.main (forwards --execute / --smoke-order / --print-plan). Prefer
`bash ~/docker-compose-up-d/run_transaction.sh` for a paper fill, or
`bash ~/docker-compose-up-d/start.sh` for the 取引画面. Both use
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
    launch_py = SRC / "bitbank_bot" / "launch.py"
    if not launch_py.is_file():
        sys.stderr.write(
            "cannot start: missing src/bitbank_bot/launch.py next to launch_bot.py.\n"
            "Clone ~/docker-compose-up-d and checkout cursor/bitbank-closed-loop-f964.\n"
            "  bash ~/docker-compose-up-d/start.sh\n"
            "Never ~/.venv. Never bash /workspace/start.sh on a Mac.\n"
        )
        return 2
    try:
        from bitbank_bot.launch import main as launch_main
    except ModuleNotFoundError:
        sys.stderr.write(
            "cannot import bitbank_bot.launch (need src/bitbank_bot/launch.py).\n"
            "Clone ~/docker-compose-up-d on branch cursor/bitbank-closed-loop-f964.\n"
            "  bash ~/docker-compose-up-d/start.sh\n"
            "Never ~/.venv. Never bash /workspace/start.sh on a Mac.\n"
        )
        return 2
    return int(launch_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
