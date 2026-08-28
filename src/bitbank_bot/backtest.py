from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from bitbank_bot.config import Settings
from bitbank_bot.decimal_utils import d
from bitbank_bot.market.candles import from_csv_rows
from bitbank_bot.models import Position
from bitbank_bot.orders.states import apply_fill
from bitbank_bot.strategy.ma_rules import MaRuleStrategy, StrategyMemory


@dataclass
class BacktestResult:
    trades: int
    wins: int
    losses: int
    realized_pnl: Decimal
    max_drawdown: Decimal
    profit_factor: Decimal
    sharpe: Decimal
    equity: list[Decimal]
    reasons: list[str]

    @property
    def win_rate(self) -> Decimal:
        closed = self.wins + self.losses
        if closed == 0:
            return Decimal("0")
        return Decimal(self.wins) / Decimal(closed)


def load_csv(path: Path) -> list:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return from_csv_rows(rows)


def run_backtest(settings: Settings, candles: list, quote: Decimal = Decimal("1000000")) -> BacktestResult:
    strategy = MaRuleStrategy(settings, StrategyMemory())
    position = Position()
    equity: list[Decimal] = []
    reasons: list[str] = []
    realized = Decimal("0")
    peak = quote
    max_dd = Decimal("0")
    wins = 0
    losses = 0
    trades = 0
    returns: list[float] = []
    prev_equity = quote

    # Feed bars incrementally so memory matches live (one new close at a time).
    min_len = settings.ema_slow + settings.slope_lookback + 2
    for i in range(min_len, len(candles) + 1):
        window = candles[:i]
        last = window[-1]
        signal = strategy.evaluate(window, position)
        price = last.close
        if signal.action == "BUY" and not position.is_open:
            amount = settings.min_btc
            cost = amount * price
            if cost <= quote:
                apply_fill(position, "buy", amount, price, last.ts, signal.take_profit_pct, signal.rule_id)
                quote -= cost
                trades += 1
                reasons.append(f"{last.ts} BUY {signal.rule_id} {signal.reason}")
        elif signal.action == "SELL" and position.is_open:
            amount = position.amount
            proceeds = amount * price
            pnl = apply_fill(position, "sell", amount, price, last.ts, None, signal.rule_id)
            quote += proceeds
            realized += pnl
            if pnl >= 0:
                wins += 1
            else:
                losses += 1
            reasons.append(f"{last.ts} SELL {signal.rule_id} pnl={pnl} {signal.reason}")
        mark = quote + (position.amount * price if position.is_open else Decimal("0"))
        equity.append(mark)
        if mark > peak:
            peak = mark
        dd = peak - mark
        if dd > max_dd:
            max_dd = dd
        if prev_equity > 0:
            returns.append(float((mark - prev_equity) / prev_equity))
        prev_equity = mark

    gross_win = Decimal("0")
    gross_loss = Decimal("0")
    # profit factor from realized only
    if realized > 0:
        gross_win = realized
    else:
        gross_loss = -realized
    # Approximate PF using win/loss counts if we only have net; keep simple:
    pf = Decimal("0")
    if losses == 0 and wins > 0:
        pf = Decimal("999")
    elif realized != 0 and losses > 0:
        avg_loss = abs(realized) / Decimal(max(losses, 1)) if realized < 0 else Decimal("1")
        avg_win = realized / Decimal(max(wins, 1)) if realized > 0 else Decimal("0")
        pf = (avg_win * wins / (avg_loss * losses)) if avg_loss > 0 and losses else Decimal("0")
        if pf < 0:
            pf = Decimal("0")
    sharpe = _sharpe(returns)
    return BacktestResult(
        trades=trades,
        wins=wins,
        losses=losses,
        realized_pnl=realized,
        max_drawdown=max_dd,
        profit_factor=pf,
        sharpe=sharpe,
        equity=equity,
        reasons=reasons,
    )


def ascii_chart(equity: list[Decimal], width: int = 60, height: int = 12) -> str:
    if not equity:
        return "(no equity)"
    values = [float(x) for x in equity]
    lo = min(values)
    hi = max(values)
    span = hi - lo or 1.0
    cols = min(width, len(values))
    step = max(1, len(values) // cols)
    sampled = values[::step][:cols]
    rows = []
    for row in range(height, -1, -1):
        thresh = lo + span * (row / height)
        line = []
        for v in sampled:
            line.append("█" if v >= thresh else " ")
        rows.append("".join(line))
    header = f"equity {d(lo)} .. {d(hi)}"
    return header + "\n" + "\n".join(rows)


def _sharpe(returns: list[float]) -> Decimal:
    if len(returns) < 2:
        return Decimal("0")
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(var)
    if std == 0:
        return Decimal("0")
    return Decimal(str(round((mean / std) * math.sqrt(365 * 24 * 12), 4)))
