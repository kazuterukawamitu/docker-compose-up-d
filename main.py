"""Command-line entry point for the Bitcoin moving-average backtester.

Examples
--------
Run the demo on a deterministic synthetic price series and save a chart::

    python main.py --plot backtest.png

Backtest against a CSV of real prices::

    python main.py --csv prices.csv --window 50 --plot backtest.png
"""

from __future__ import annotations

import argparse
import sys

from mlbot import (
    Backtester,
    MovingAverageStrategy,
    StrategyParams,
    generate_price_series,
    load_price_series,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", help="CSV file with a price column (default: synthetic data)")
    parser.add_argument("--column", default="close", help="Price column name in the CSV")
    parser.add_argument("--periods", type=int, default=2000, help="Synthetic series length")
    parser.add_argument("--seed", type=int, default=42, help="Synthetic series RNG seed")
    parser.add_argument("--window", type=int, default=50, help="Moving-average window")
    parser.add_argument("--cash", type=float, default=10_000.0, help="Initial cash")
    parser.add_argument("--fee", type=float, default=0.0005, help="Per-side trade fee (fraction)")
    parser.add_argument("--plot", help="Path to save a PNG chart of the backtest")
    return parser.parse_args(argv)


def make_plot(signals, result, path: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax_price, ax_equity) = plt.subplots(
        2, 1, figsize=(12, 8), sharex=True, gridspec_kw={"height_ratios": [2, 1]}
    )

    ax_price.plot(signals.index, signals["close"], label="BTC close", color="#1f77b4", lw=1)
    ax_price.plot(signals.index, signals["sma"], label="SMA", color="#ff7f0e", lw=1.2)

    entries = [t.entry_time for t in result.trades]
    entry_prices = [t.entry_price for t in result.trades]
    exits = [t.exit_time for t in result.trades]
    exit_prices = [t.exit_price for t in result.trades]
    ax_price.scatter(entries, entry_prices, marker="^", color="green", s=60, label="Buy", zorder=5)
    ax_price.scatter(exits, exit_prices, marker="v", color="red", s=60, label="Sell", zorder=5)
    ax_price.set_ylabel("Price")
    ax_price.set_title("Bitcoin moving-average strategy backtest")
    ax_price.legend(loc="upper left")
    ax_price.grid(alpha=0.3)

    ax_equity.plot(result.equity_curve.index, result.equity_curve, color="#2ca02c", label="Equity")
    ax_equity.axhline(result.initial_cash, color="gray", ls="--", lw=1, label="Initial cash")
    ax_equity.set_ylabel("Equity")
    ax_equity.set_xlabel("Time")
    ax_equity.legend(loc="upper left")
    ax_equity.grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(path, dpi=120)
    print(f"Saved chart to {path}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.csv:
        df = load_price_series(args.csv, column=args.column)
        print(f"Loaded {len(df)} rows from {args.csv}")
    else:
        df = generate_price_series(periods=args.periods, seed=args.seed)
        print(f"Generated {len(df)} rows of synthetic BTC price data (seed={args.seed})")

    strategy = MovingAverageStrategy(StrategyParams(window=args.window))
    backtester = Backtester(strategy=strategy, initial_cash=args.cash, fee=args.fee)
    result = backtester.run(df)

    print()
    print(result.summary())

    if args.plot:
        signals = strategy.generate_signals(df)
        make_plot(signals, result, args.plot)

    return 0


if __name__ == "__main__":
    sys.exit(main())
