"""python -m bitbank_bot (works from repo root or src/)."""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent
_ROOT = _SRC.parent
for candidate in (_SRC, _ROOT / "src"):
    if (candidate / "bitbank_bot" / "main.py").is_file() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
        break

from bitbank_bot.main import main

if __name__ == "__main__":
    raise SystemExit(main())
