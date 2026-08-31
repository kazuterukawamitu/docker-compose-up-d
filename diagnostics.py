#!/usr/bin/env python3
"""Read-only diagnostics from the repo root. Never places an order."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bitbank_bot.diagnostics import main

if __name__ == "__main__":
    raise SystemExit(main())
