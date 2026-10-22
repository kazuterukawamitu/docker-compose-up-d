"""Fill notional and fee math. Gross exchange notional stays separate from fees."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN

from bitbank_bot.money import D, ZERO

_NOTIONAL_QUANTUM = Decimal("0.00000001")


def incremental_notional(
    prev_qty: Decimal,
    prev_avg: Decimal,
    new_qty: Decimal,
    new_avg: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    """Return (delta_qty, delta_notional, incremental_avg).

    Bitbank reports a cumulative average. Booking ``delta_qty * cumulative_avg``
    understates a later fill when the price rises, and overstates it when the
    price falls. The new notional minus the previous notional is the increment.
    """
    prev_qty = D(prev_qty)
    prev_avg = D(prev_avg)
    new_qty = D(new_qty)
    new_avg = D(new_avg)
    delta_qty = new_qty - prev_qty
    if delta_qty <= ZERO:
        return ZERO, ZERO, ZERO
    if prev_qty > ZERO and prev_avg <= ZERO:
        prev_avg = new_avg
    delta_notional = (new_qty * new_avg) - (prev_qty * prev_avg)
    if delta_notional <= ZERO:
        delta_notional = delta_qty * new_avg
    delta_notional = delta_notional.quantize(_NOTIONAL_QUANTUM, rounding=ROUND_HALF_EVEN)
    incremental_avg = delta_notional / delta_qty
    return delta_qty, delta_notional, incremental_avg


def fill_fee_jpy(notional: Decimal, rate: Decimal) -> Decimal:
    notional = D(notional)
    rate = D(rate)
    if notional <= ZERO or rate == ZERO:
        return ZERO
    fee = notional * rate
    return fee if fee > ZERO else ZERO


def round_trip_cost_rate(taker_rate: Decimal) -> Decimal:
    return D(taker_rate) * 2


def expected_net_jpy(notional: Decimal, tp_pct: Decimal, taker_rate: Decimal) -> Decimal:
    """Gross target minus a taker fee on the entry and on the exit."""
    notional = D(notional)
    gross = notional * D(tp_pct)
    return gross - (notional * round_trip_cost_rate(taker_rate))


def fee_allows_target(tp_pct: Decimal, round_trip: Decimal) -> bool:
    return D(tp_pct) > D(round_trip)
