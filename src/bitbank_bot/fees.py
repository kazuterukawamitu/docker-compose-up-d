"""Actual or estimated trade fees. Never treat TARGET as a fill."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from bitbank_bot.money import D, ZERO


def fee_from_raw(raw: Mapping[str, Any] | None, notional_jpy: Decimal) -> Decimal:
    """Prefer exchange fee fields; otherwise return ZERO (caller may estimate)."""
    if not raw:
        return ZERO
    for key in (
        "fee_amount_quote",
        "fee_occurred_amount_quote",
        "fee_quote",
        "fee",
    ):
        if raw.get(key) not in (None, ""):
            value = D(raw.get(key))
            if value >= ZERO:
                return value
    return ZERO


def estimate_fee(notional_jpy: Decimal, fee_rate: Decimal) -> Decimal:
    notional = D(notional_jpy)
    rate = D(fee_rate)
    if notional <= ZERO or rate <= ZERO:
        return ZERO
    return notional * rate


def resolve_fee(
    raw: Mapping[str, Any] | None,
    notional_jpy: Decimal,
    fee_rate: Decimal,
    *,
    prefer_estimate: bool = False,
) -> Decimal:
    if prefer_estimate:
        return estimate_fee(notional_jpy, fee_rate)
    actual = fee_from_raw(raw, notional_jpy)
    if actual > ZERO:
        return actual
    return estimate_fee(notional_jpy, fee_rate)


def round_trip_fee_pct(fee_rate: Decimal) -> Decimal:
    """Buy + sell fee haircut as a fraction of notional."""
    return D(fee_rate) * D(2)


def tp_covers_fees(tp_pct: Decimal, fee_rate: Decimal) -> bool:
    return D(tp_pct) > round_trip_fee_pct(fee_rate)
