"""CLI: python -m bitbank_bot [run|preflight|backtest]."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from bitbank_bot.config import load_settings
from bitbank_bot.exchange.rest import BitbankRest
from bitbank_bot.lock import InstanceLock
from bitbank_bot.logging_config import setup_logging
from bitbank_bot.trader import Trader


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bitbank BTC/JPY bot (dry-run by default)")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("run", help="start the trading loop")
    sub.add_parser("preflight", help="check public API / balances, no orders")
    bt = sub.add_parser("backtest", help="replay a local OHLCV CSV")
    bt.add_argument("csv", type=Path)
    args = parser.parse_args(argv)
    cmd = args.cmd or "run"
    settings = load_settings()
    setup_logging(settings.log_dir, settings.log_level)
    log = logging.getLogger("bitbank_bot")
    if cmd == "backtest":
        from decimal import Decimal

        from bitbank_bot.backtest import load_candles_csv, run_backtest

        candles = load_candles_csv(args.csv)
        metrics = run_backtest(candles, settings)
        log.info("backtest %s", metrics)
        print(metrics)
        return 0

    async def _async() -> int:
        async with BitbankRest(settings) as rest:
            if cmd == "preflight":
                from bitbank_bot.preflight import run_preflight

                report = await run_preflight(settings, rest)
                print(report)
                return 0
            with InstanceLock(settings.lock_file):
                trader = Trader(settings, rest)
                await trader.run()
            return 0

    try:
        return asyncio.run(_async())
    except KeyboardInterrupt:
        log.info("stopped")
        return 0


if __name__ == "__main__":
    sys.exit(main())
