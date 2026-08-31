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

from bitbank_bot.main import main

if __name__ == "__main__":
    raise SystemExit(main())
