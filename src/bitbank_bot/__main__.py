"""python -m bitbank_bot

Bootstraps ``src/`` when this file is executed as a script, then starts the
bot through the package launcher (default DRY_RUN).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent
if _SRC.name == "src" and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bitbank_bot.launch import main

if __name__ == "__main__":
    raise SystemExit(main())
