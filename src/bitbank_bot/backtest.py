"""CSV / candle playback using the live strategy + amount helpers."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from bitbank_bot.amounts import plan_buy, plan_sell
from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.market_data import Candle, candles_from_csv
from bitbank_bot.money import D, ZERO
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import Position, Strategy, build_snapshots


@dataclass
class BacktestReport:
    trades: int
    wins: int
    losses: int
    win_rate: Decimal
    profit_factor: Decimal
    max_drawdown: Decimal
    net_pnl: Decimal
    equity: Decimal


def load_csv(path: Path) -> list[Candle]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = csv.reader(fh)
        return candles_from_csv(rows)


def run_backtest(
    candles: list[Candle],
    cfg: Config,
    initial_jpy: Decimal = D("1000000"),
) -> BacktestReport:
    closes = [c.close for c in candles]
    stamps = [c.timestamp_ms for c in candles]
    snaps = build_snapshots(closes, stamps, cfg)
    strategy = Strategy(cfg)
    risk = RiskManager(cfg, killed=False)
    cash = D(initial_jpy)
    btc = ZERO
    position: Position | None = None
    peak = cash
    max_dd = ZERO
    wins = 0
    losses = 0
    gross_win = ZERO
    gross_loss = ZERO
    trades = 0
    for snap in snaps:
        signal = strategy.evaluate(snap, position)
        if signal.side == "buy" and position is None:
            plan = plan_buy(
                available_jpy=cash,
                available_btc=btc,
                price=snap.close,
                cfg=cfg,
                risk=risk,
            )
            if not plan.ok:
                continue
            cash -= plan.planned_order_jpy
            btc += plan.amount
            position = Position(
                amount=plan.amount,
                average_price=snap.close,
                tp_pct=signal.tp_pct or cfg.buy1_tp,
                entry_candle_index=snap.index,
                entry_candle_ts=snap.timestamp_ms,
                actual_execution_jpy=plan.planned_order_jpy,
                kind=signal.kind,
            )
        elif signal.side == "sell" and position is not None:
            plan = plan_sell(
                available_jpy=cash,
                available_btc=position.amount,
                price=snap.close,
                cfg=cfg,
                risk=risk,
            )
            if not plan.ok:
                continue
            proceeds = plan.amount * snap.close
            pnl = proceeds - position.actual_execution_jpy
            cash += proceeds
            btc -= plan.amount
            risk.record_realized_pnl(pnl)
            trades += 1
            if pnl >= ZERO:
                wins += 1
                gross_win += pnl
            else:
                losses += 1
                gross_loss += -pnl
            position = None
        equity = cash + btc * snap.close
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
    if position is not None and snaps:
        last = snaps[-1].close
        cash += position.amount * last
        pnl = position.amount * last - position.actual_execution_jpy
        trades += 1
        if pnl >= ZERO:
            wins += 1
            gross_win += pnl
        else:
            losses += 1
            gross_loss += -pnl
    equity = cash
    win_rate = D(wins) / D(trades) if trades else ZERO
    pf = (gross_win / gross_loss) if gross_loss > ZERO else (D("999") if gross_win > ZERO else ZERO)
    net = equity - D(initial_jpy)
    slog(
        "STRATEGY",
        "backtest done",
        trades=trades,
        win_rate=str(win_rate),
        pf=str(pf),
        max_dd=str(max_dd),
        net=str(net),
    )
    return BacktestReport(trades, wins, losses, win_rate, pf, max_dd, net, equity)
