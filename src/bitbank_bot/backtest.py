"""Replay README MA rules over candles. Never places orders."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from bitbank_bot.adaptive import adaptive_basin_hopping
from bitbank_bot.config import Config
from bitbank_bot.fees import fill_fee_jpy
from bitbank_bot.market_data import Candle
from bitbank_bot.money import D, ZERO
from bitbank_bot.strategy import Position, Strategy, build_snapshots


@dataclass
class BacktestReport:
    trades: int
    wins: int
    losses: int
    win_rate: float
    net_jpy: Decimal
    max_drawdown_jpy: Decimal
    suggested_slope: Decimal = ZERO


def run_backtest(candles: list[Candle], cfg: Config) -> BacktestReport:
    closes = [c.close for c in candles]
    stamps = [c.timestamp_ms for c in candles]
    snaps = build_snapshots(closes, stamps, cfg)
    strategy = Strategy(cfg)
    position: Position | None = None
    trades = 0
    wins = 0
    losses = 0
    net = ZERO
    equity = ZERO
    peak = ZERO
    max_dd = ZERO
    for snap in snaps:
        signal = strategy.evaluate(snap, position)
        if signal.side == "buy" and position is None:
            amount = D("0.001")
            notional = amount * snap.close
            position = Position(
                amount=amount,
                average_price=snap.close,
                tp_pct=signal.tp_pct or cfg.buy1_tp,
                entry_candle_index=snap.index,
                entry_candle_ts=snap.timestamp_ms,
                actual_execution_jpy=notional,
                kind=signal.kind,
                fees_jpy=fill_fee_jpy(notional, cfg.taker_fee_rate),
            )
            continue
        if signal.side == "sell" and position is not None:
            proceeds = position.amount * snap.close
            sell_fee = fill_fee_jpy(proceeds, cfg.taker_fee_rate)
            pnl = (proceeds - sell_fee) - position.actual_execution_jpy - position.fees_jpy
            net += pnl
            equity += pnl
            trades += 1
            if pnl >= ZERO:
                wins += 1
            else:
                losses += 1
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd
            position = None
    win_rate = (wins / trades) if trades else 0.0
    slope = adaptive_basin_hopping(closes, cfg.ma_slope_threshold)
    return BacktestReport(trades, wins, losses, win_rate, net, max_dd, slope)


def report_lines(report: BacktestReport) -> list[str]:
    return [
        f"trades={report.trades}",
        f"wins={report.wins}",
        f"losses={report.losses}",
        f"win_rate={report.win_rate:.4f}",
        f"net_jpy={report.net_jpy}",
        f"max_drawdown_jpy={report.max_drawdown_jpy}",
        f"suggested_slope={report.suggested_slope}",
    ]
