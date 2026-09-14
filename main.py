#!/usr/bin/env python3
"""Repo-root launcher. Prefer `python3 launch.py`.

    python3 launch.py
    python3 main.py
    python3 run.py

All three stay DRY_RUN unless .env is fully armed for LIVE. None of these
files place a Bitbank order by themselves.
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
