"""CSV / candle playback using the live strategy + amount helpers."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
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
class ClosedTrade:
    kind: str
    entry_ts: int
    exit_ts: int
    entry_price: Decimal
    exit_price: Decimal
    amount: Decimal
    pnl: Decimal
    reason: str


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
    blocked_buys: int = 0
    last_block_reason: str = ""
    closed: list[ClosedTrade] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "trades": self.trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": str(self.win_rate),
            "profit_factor": str(self.profit_factor),
            "max_drawdown": str(self.max_drawdown),
            "net_pnl": str(self.net_pnl),
            "equity": str(self.equity),
            "blocked_buys": self.blocked_buys,
            "last_block_reason": self.last_block_reason,
            "closed": [
                {
                    "kind": t.kind,
                    "entry_ts": t.entry_ts,
                    "exit_ts": t.exit_ts,
                    "entry_price": str(t.entry_price),
                    "exit_price": str(t.exit_price),
                    "amount": str(t.amount),
                    "pnl": str(t.pnl),
                    "reason": t.reason,
                }
                for t in self.closed
            ],
        }


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
    blocked_buys = 0
    last_block_reason = ""
    closed: list[ClosedTrade] = []
    for snap in snaps:
        risk.set_as_of(snap.timestamp_ms)
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
                blocked_buys += 1
                last_block_reason = plan.reason
                slog("RISK", "backtest buy blocked", reason=plan.reason)
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
                last_block_reason = plan.reason
                continue
            proceeds = plan.amount * snap.close
            pnl = proceeds - position.actual_execution_jpy
            cash += proceeds
            btc -= plan.amount
            risk.record_realized_pnl(pnl)
            trades += 1
            closed.append(
                ClosedTrade(
                    kind=position.kind,
                    entry_ts=position.entry_candle_ts,
                    exit_ts=snap.timestamp_ms,
                    entry_price=position.average_price,
                    exit_price=snap.close,
                    amount=plan.amount,
                    pnl=pnl,
                    reason=signal.kind,
                )
            )
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
        closed.append(
            ClosedTrade(
                kind=position.kind,
                entry_ts=position.entry_candle_ts,
                exit_ts=snaps[-1].timestamp_ms,
                entry_price=position.average_price,
                exit_price=last,
                amount=position.amount,
                pnl=pnl,
                reason="mark_to_market",
            )
        )
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
        blocked_buys=blocked_buys,
        last_block_reason=last_block_reason or "-",
    )
    return BacktestReport(
        trades,
        wins,
        losses,
        win_rate,
        pf,
        max_dd,
        net,
        equity,
        blocked_buys=blocked_buys,
        last_block_reason=last_block_reason,
        closed=closed,
    )
