#!/usr/bin/env python3
"""Start the Bitbank btc_jpy closed-loop bot (DRY_RUN by default).

Working launchers (run from the repository root):

    python3 closed_loop.py
    python3 closed_loop.py --verify
    python3 closed_loop.py --verify --no-public
    python3 closed_loop.py --review
    python3 main.py
    python3 src/bitbank_bot/main.py
    python3 -m bitbank_bot
    bash ./start.sh --screen

None of these place a live Bitbank order unless .env has DRY_RUN=false,
LIVE_TRADING=true, keys, and LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


REVIEW = """LAUNCH_OK  Bitbank BTC/JPY closed-loop bot

Run this from the repository root (the folder that contains main.py):

  python3 closed_loop.py --dry-run --skip-lock --no-screen --max-cycles 1

That starts the full package once, prints JSON, and exits. HOLD/no_buy_setup
is normal. For a continuous 取引画面 on a Mac iTerm TTY:

  bash ./start.sh --screen

Other entry points (same bot, still DRY_RUN by default):
  python3 main.py
  python3 src/bitbank_bot/main.py
  python3 -m bitbank_bot
  python3 run.py                    # stdlib screen only; never create_order

Checks:
  python3 closed_loop.py --verify
  python3 closed_loop.py --verify --no-public

Live POST is not implied by any of these commands.

Added by the closed-loop work: trade_signal_executor, execution_gate,
rate_engine, hold_tracer, trade_trace, reconciliation, this launcher.
Not removed: run.py, engine.py, BUY1-4/SELL1-4, HTF filter.
Not built: Sentry, extra exchanges, concatenated all-in-one dump.
"""


def _banner(command: str) -> None:
    sys.stderr.write(
        f"LAUNCH_OK  {command}\n"
        "Bitbank BTC/JPY  DRY_RUN (no live orders). HOLD/WAIT is normal. Ctrl-C to stop.\n"
    )
    sys.stderr.flush()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--review" in args:
        sys.stdout.write(REVIEW)
        sys.stdout.flush()
        return 0

    verify = "--verify" in args
    no_public = "--no-public" in args
    args = [a for a in args if a not in {"--verify", "--no-public", "--review"}]

    if verify:
        forwarded = ["--once", "--skip-lock", "--no-screen", "--dry-run"]
        if no_public:
            forwarded.append("--synthetic")
        forwarded.extend(args)
        _banner("python3 closed_loop.py --verify" + (" --no-public" if no_public else ""))
        from bitbank_bot.main import main as bot_main

        return int(bot_main(forwarded))

    if no_public:
        sys.stderr.write("--no-public is only valid with --verify\n")
        return 2

    _banner("python3 closed_loop.py")
    from bitbank_bot.main import main as bot_main

    return int(bot_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
