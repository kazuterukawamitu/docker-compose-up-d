#!/usr/bin/env python3
"""Repo-root alias for launch.py. Prefer `python3 launch.py` or `bash start.sh`.

Do not run `python3 main.py` from your home folder. ~/main.py is often a
different program. This file only works inside the Bitbank git checkout.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from launch import main as launch_main

if __name__ == "__main__":
    raise SystemExit(launch_main())
