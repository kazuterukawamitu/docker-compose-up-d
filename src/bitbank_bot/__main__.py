from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from bitbank_bot.backtest import ascii_chart, load_csv, run_backtest
from bitbank_bot.bot import TradingBot, install_signal_handlers
from bitbank_bot.config import load_settings
from bitbank_bot.logging_setup import setup_logging
from bitbank_bot.preflight import run_preflight


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bitbank BTC/JPY README-rule bot")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--preflight", action="store_true", help="connectivity checks; no orders")
    parser.add_argument("--private", action="store_true", help="include private asset check in preflight")
    parser.add_argument("--once", action="store_true", help="run a single evaluate/order cycle")
    parser.add_argument("--backtest", metavar="CSV", help="replay README rules on OHLCV CSV")
    args = parser.parse_args(argv)

    settings = load_settings(args.env_file)
    setup_logging(settings.log_dir, settings.log_level)
    log = logging.getLogger("bitbank_bot")
    log.info("starting dry_run=%s pair=%s candle=%s", settings.dry_run, settings.pair, settings.candle_type)

    if args.backtest:
        candles = load_csv(Path(args.backtest))
        result = run_backtest(settings, candles)
        print(f"trades={result.trades} wins={result.wins} losses={result.losses} wr={result.win_rate}")
        print(f"realized_pnl={result.realized_pnl} max_dd={result.max_drawdown} pf={result.profit_factor} sharpe={result.sharpe}")
        print(ascii_chart(result.equity))
        for line in result.reasons[-20:]:
            print(line)
        return 0

    if args.preflight:
        report = asyncio.run(run_preflight(settings, include_private=args.private))
        for check in report.checks:
            mark = "OK" if check.ok else "FAIL"
            print(f"{mark:4} {check.name}: {check.detail}")
        return 0 if report.ok else 1

    return asyncio.run(_run_bot(settings, once=args.once))


async def _run_bot(settings, once: bool) -> int:
    bot = TradingBot(settings)
    install_signal_handlers(bot)
    await bot.run(once=once)
    return 0


if __name__ == "__main__":
    sys.exit(main())
