#!/usr/bin/env python3
"""Startup-style Bitbank BTC/JPY program.

Default starts the bot (DRY_RUN unless .env is LIVE). Review / verify are
opt-in. This file never flips LIVE on.

    python3 closed_loop.py
    python3 closed_loop.py --once --synthetic --skip-lock --no-screen
    python3 closed_loop.py --verify --no-public
    python3 closed_loop.py --review

Order POST happens only when DRY_RUN=false, LIVE_TRADING=true, keys, and
LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK, plus a real BUY/SELL.
may_place_live_orders stays false unless that whole set is present.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bitbank_bot.closed_loop import PROGRAM_REVIEW, review, verify as _verify
from bitbank_bot.launch import main as launch_main


def verify(*, public: bool = True) -> int:
    return _verify(public=public, root=ROOT)


def main(argv: list[str] | None = None) -> int:
    return launch_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
