#!/usr/bin/env python3
"""Repo-root launcher so `python3 main.py` works from the clone.

Adds `src/` to sys.path. Default mode remains DRY_RUN (no live orders).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from bitbank_bot.main import main
except ModuleNotFoundError as exc:
    sys.stderr.write(
        f"Missing Python package ({exc.name}). Do not use system python3.\n"
        "Paste this ONE line in iTerm (not several commands):\n"
        "  bash ~/docker-compose-up-d/start.sh\n"
    )
    raise SystemExit(2) from exc

if __name__ == "__main__":
    raise SystemExit(main())
