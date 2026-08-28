from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from bitbank_bot.config import Settings
from bitbank_bot.decimal_utils import clamp_non_negative, quantize_btc, quantize_price
from bitbank_bot.models import Signal, Snapshot


@dataclass(frozen=True)
class SizePlan:
    target: Decimal
    planned: Decimal
    price: Decimal | None
    blocked: str = ""


def plan_size(settings: Settings, signal: Signal, snapshot: Snapshot) -> SizePlan:
    last = snapshot.ticker.last
    if last <= 0:
        return SizePlan(Decimal("0"), Decimal("0"), None, "invalid last price")

    if signal.action == "BUY":
        ask = snapshot.ticker.sell if snapshot.ticker.sell > 0 else last
        price = quantize_price(ask)
        remaining_cap = clamp_non_negative(settings.max_position_btc - snapshot.position.amount)
        if remaining_cap < settings.min_btc:
            return SizePlan(Decimal("0"), Decimal("0"), price, "position cap below min size")
        affordable = (snapshot.jpy_free * settings.balance_usage_ratio) / price
        if signal.target_kind == "max_available":
            target = remaining_cap
        else:
            target = settings.min_btc
        planned = quantize_btc(min(target, remaining_cap, affordable), settings.min_btc)
        if planned < settings.min_btc:
            return SizePlan(target, Decimal("0"), price, "insufficient JPY for min size")
        return SizePlan(target, planned, price)

    if signal.action == "SELL":
        bid = snapshot.ticker.buy if snapshot.ticker.buy > 0 else last
        price = quantize_price(bid)
        available = min(snapshot.btc_free, snapshot.position.amount if snapshot.position.amount > 0 else snapshot.btc_free)
        available = available * settings.balance_usage_ratio if signal.target_kind != "flatten" else available
        target = available
        planned = quantize_btc(available, settings.min_btc)
        if planned < settings.min_btc:
            return SizePlan(target, Decimal("0"), price, "BTC below min size")
        return SizePlan(target, planned, price)

    return SizePlan(Decimal("0"), Decimal("0"), None, "hold")
