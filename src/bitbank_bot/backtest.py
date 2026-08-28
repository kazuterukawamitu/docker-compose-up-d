"""CSV backtest for the Granville/README rules. Writes equity metrics, not live orders."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pandas as pd

from bitbank_bot.config import Settings
from bitbank_bot.market.candles import build_snapshot
from bitbank_bot.models import Candle, Side, Ticker
from bitbank_bot.orders.amount import buyable_btc
from bitbank_bot.risk.manager import RiskManager
from bitbank_bot.strategy.plugins import build_strategies


def load_candles_csv(path: Path) -> list[Candle]:
    frame = pd.read_csv(path)
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {sorted(missing)}")
    candles: list[Candle] = []
    for row in frame.itertuples(index=False):
        ts = int(row.timestamp)
        if ts < 10_000_000_000:
            ts *= 1000
        candles.append(
            Candle(
                timestamp_ms=ts,
                open=Decimal(str(row.open)),
                high=Decimal(str(row.high)),
                low=Decimal(str(row.low)),
                close=Decimal(str(row.close)),
                volume=Decimal(str(row.volume)),
            )
        )
    return candles


def run_backtest(
    candles: list[Candle],
    settings: Settings,
    starting_jpy: Decimal = Decimal("1000000"),
) -> dict[str, float]:
    strategy = build_strategies(settings)
    risk = RiskManager(settings)
    jpy = starting_jpy
    btc = Decimal("0")
    equity_curve: list[float] = []
    wins = 0
    losses = 0
    gross_win = Decimal("0")
    gross_loss = Decimal("0")
    entry: Decimal | None = None
    peak = float(starting_jpy)
    max_dd = 0.0

    from bitbank_bot.models import Position

    position = Position(pair=settings.pair)

    for i in range(settings.slow_ma + 2, len(candles) + 1):
        window = candles[:i]
        last = window[-1]
        ticker = Ticker(
            pair=settings.pair,
            last=last.close,
            bid=last.close,
            ask=last.close,
            high=last.high,
            low=last.low,
            volume=last.volume,
            timestamp_ms=last.timestamp_ms,
        )
        snapshot = build_snapshot(window, ticker, settings)
        signal = strategy.evaluate(snapshot)
        decision = risk.approve(signal, position, ticker, jpy, btc)
        px = last.close
        if decision.allowed and decision.signal.side is Side.BUY and btc == 0:
            amount = buyable_btc(jpy, px, settings)
            amount = risk.cap_buy_amount(amount, btc)
            if amount >= settings.min_order_btc:
                cost = amount * px
                jpy -= cost
                btc = amount
                entry = px
                position.amount_btc = btc
                position.entry_price = px
                position.take_profit_pct = decision.signal.take_profit_pct
                position.high_water = px
        elif decision.allowed and decision.signal.side is Side.SELL and btc > 0:
            proceeds = btc * px
            pnl = proceeds - (entry or px) * btc
            jpy += proceeds
            if pnl >= 0:
                wins += 1
                gross_win += pnl
            else:
                losses += 1
                gross_loss += -pnl
            btc = Decimal("0")
            entry = None
            position = Position(pair=settings.pair)

        equity = float(jpy + btc * px)
        equity_curve.append(equity)
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)

    returns = []
    for a, b in zip(equity_curve, equity_curve[1:]):
        if a:
            returns.append((b - a) / a)
    sharpe = 0.0
    if len(returns) > 2:
        import numpy as np

        arr = np.array(returns)
        std = arr.std()
        if std > 0:
            sharpe = float((arr.mean() / std) * (len(arr) ** 0.5))
    pf = float(gross_win / gross_loss) if gross_loss > 0 else (float(gross_win) if gross_win > 0 else 0.0)
    return {
        "bars": float(len(candles)),
        "final_equity": equity_curve[-1] if equity_curve else float(starting_jpy),
        "profit_factor": pf,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "wins": float(wins),
        "losses": float(losses),
    }


def plot_equity(equity: list[float], dest: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    dest.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(10, 4))
    plt.plot(equity)
    plt.title("Backtest equity")
    plt.tight_layout()
    plt.savefig(dest)
    plt.close()
