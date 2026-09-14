#!/usr/bin/env python3
"""Alias for launch.py so `python3 main.py` is the same program.

    python3 main.py
    python3 launch.py
    bash ./start.sh

Default stays DRY_RUN. Neither places a Bitbank order unless --live and keys.
"""

from __future__ import annotations

from launch import main

if __name__ == "__main__":
    raise SystemExit(main())
