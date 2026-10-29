"""Observed decision layer for entries and protective exits.

Granville (moving-average) signals stay the entry rules. This module adds the
checks that those rules do not do on their own:

* update confidence with Shannon entropy of recent returns
* block a buy when the configured take-profit does not clear round-trip fees
* exit on a live price when stop or take-profit is hit, without waiting for
  the next closed candle

Nothing here places an order. The engine still has to pass the risk manager
and the order gate.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Sequence

from bitbank_bot.money import D, ONE, ZERO, pct_offset
from bitbank_bot.strategy import Position, Signal


def shannon_entropy(closes: Sequence[Decimal], bins: int = 8) -> Decimal:
    """Normalized Shannon entropy of recent returns, in ``[0, 1]``.

    0 means every return landed in the same bin. 1 means they are spread
    evenly. Too few closes returns 0 so a short history cannot block entries.
    """
    if bins < 2 or len(closes) < 3:
        return ZERO
    returns: list[float] = []
    for prev, close in zip(closes, closes[1:]):
        prev_d = D(prev)
        if prev_d == ZERO:
            continue
        returns.append(float((D(close) - prev_d) / prev_d))
    if len(returns) < 2:
        return ZERO
    lo, hi = -0.02, 0.02
    width = (hi - lo) / bins
    counts = [0] * bins
    for value in returns:
        if value <= lo:
            index = 0
        elif value >= hi:
            index = bins - 1
        else:
            index = min(bins - 1, int((value - lo) / width))
        counts[index] += 1
    total = sum(counts)
    if total <= 0:
        return ZERO
    entropy = 0.0
    for count in counts:
        if count <= 0:
            continue
        probability = count / total
        entropy -= probability * math.log2(probability)
    scale = math.log2(bins)
    if scale <= 0:
        return ZERO
    return D(str(entropy / scale))


def required_edge(fee_rate: Decimal, entropy: Decimal) -> Decimal:
    """Round-trip taker cost, widened when recent returns are disordered."""
    return (D(fee_rate) * 2) * (ONE + D(entropy))


def buy_block_reason(
    tp_pct: Decimal | None,
    fee_rate: Decimal,
    entropy: Decimal,
) -> str | None:
    """Refuse a buy whose take-profit does not clear fees.

    Granville still decides *whether* a setup exists. This only rejects a
    setup that cannot pay the round trip. Sells are never blocked here.
    """
    need = required_edge(fee_rate, entropy)
    if D(tp_pct or 0) <= need:
        return "fee_exceeds_edge"
    return None


def unrealized_jpy(position: Position, mark: Decimal, fee_rate: Decimal) -> Decimal:
    """Mark-to-market JPY after the entry fee and an estimated exit fee."""
    proceeds = position.amount * D(mark)
    exit_fee = proceeds * D(fee_rate)
    return proceeds - exit_fee - position.actual_execution_jpy - position.fee_jpy


def price_exit(
    position: Position,
    mark: Decimal,
    *,
    stop_loss_pct: Decimal,
    taker_fee_rate: Decimal,
    max_daily_loss_jpy: Decimal = ZERO,
    daily_pnl_floor: Decimal = ZERO,
    daily_pnl: Decimal = ZERO,
) -> Signal | None:
    """Live-price stop, daily-loss flatten, or fee-aware take-profit.

    Stop and daily-loss flatten ignore the entry candle. Take-profit fires
    only when the mark is at the configured target and the exit is still
    profitable after fees. Pattern sells (SELL1–4) are not produced here.
    """
    mark_d = D(mark)
    if mark_d <= ZERO or position.amount <= ZERO or position.average_price <= ZERO:
        return None
    stop_pct = D(stop_loss_pct)
    if stop_pct > ZERO:
        stop_px = position.average_price * (ONE - stop_pct)
        if mark_d <= stop_px:
            return Signal(
                "STOP",
                "sell",
                None,
                f"stop mark={mark_d} <= {stop_px} (avg={position.average_price})",
            )
    loss_limit = D(max_daily_loss_jpy)
    floor = D(daily_pnl_floor)
    open_pnl = unrealized_jpy(position, mark_d, taker_fee_rate)
    day = D(daily_pnl) + open_pnl
    if loss_limit > ZERO and day <= -loss_limit:
        return Signal(
            "STOP",
            "sell",
            None,
            f"daily_pnl_flatten day={day} limit={loss_limit}",
        )
    if floor > ZERO and day <= -floor:
        return Signal(
            "STOP",
            "sell",
            None,
            f"daily_pnl_floor_flatten day={day} floor={floor}",
        )
    target = pct_offset(position.average_price, position.tp_pct)
    if mark_d >= target:
        if open_pnl <= ZERO:
            return None
        return Signal(
            "TP",
            "sell",
            position.tp_pct,
            (
                f"take profit mark={mark_d} >= {target} "
                f"net={open_pnl} (fill_avg={position.average_price})"
            ),
        )
    return None
