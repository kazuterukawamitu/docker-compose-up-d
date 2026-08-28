"""Size BTC/JPY orders with Decimal quantization and fee/safety haircut."""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from bitbank_bot.config import MIN_ORDER_BTC, PRICE_TICK, Settings
from bitbank_bot.exceptions import InsufficientFundsError
from bitbank_bot.models import OrderType, Side


def quantize_btc(amount: Decimal, step: Decimal = MIN_ORDER_BTC) -> Decimal:
    if amount <= 0:
        return Decimal("0")
    units = (amount / step).to_integral_value(rounding=ROUND_DOWN)
    return units * step


def quantize_price(price: Decimal, tick: Decimal = PRICE_TICK) -> Decimal:
    units = (price / tick).to_integral_value(rounding=ROUND_DOWN)
    return units * tick


def buyable_btc(
    jpy_free: Decimal,
    price: Decimal,
    settings: Settings,
) -> Decimal:
    if price <= 0:
        return Decimal("0")
    haircut = Decimal("1") - settings.taker_fee_rate - settings.safety_margin
    if haircut <= 0:
        return Decimal("0")
    raw = (jpy_free * haircut) / price
    return quantize_btc(raw, settings.min_order_btc)


def sellable_btc(btc_free: Decimal, settings: Settings) -> Decimal:
    return quantize_btc(btc_free, settings.min_order_btc)


def market_buy_jpy(jpy_free: Decimal, settings: Settings) -> Decimal:
    haircut = Decimal("1") - settings.taker_fee_rate - settings.safety_margin
    yen = (jpy_free * haircut).to_integral_value(rounding=ROUND_DOWN)
    return Decimal(yen)


def validate_order_amount(
    side: Side,
    amount_btc: Decimal,
    price: Decimal,
    jpy_free: Decimal,
    btc_free: Decimal,
    settings: Settings,
) -> Decimal:
    min_btc = settings.min_order_btc
    if side is Side.BUY:
        sized = min(amount_btc, buyable_btc(jpy_free, price, settings))
        sized = quantize_btc(sized, min_btc)
        if sized < min_btc:
            raise InsufficientFundsError(
                f"buy amount {sized} BTC below minimum {min_btc} BTC"
            )
        notional = sized * price
        if notional > jpy_free:
            raise InsufficientFundsError("insufficient JPY for buy")
        return sized
    sized = min(amount_btc, sellable_btc(btc_free, settings))
    if sized < min_btc:
        raise InsufficientFundsError(f"sell amount {sized} BTC below minimum {min_btc} BTC")
    return sized


def limit_price(side: Side, ticker_last: Decimal, bid: Decimal, ask: Decimal) -> Decimal:
    if side is Side.BUY:
        px = ask if ask > 0 else ticker_last
    else:
        px = bid if bid > 0 else ticker_last
    return quantize_price(px)


def order_payload_amount(
    side: Side,
    order_type: OrderType,
    amount_btc: Decimal,
    price: Decimal,
    settings: Settings,
) -> Decimal:
    """Bitbank market buys are denominated in JPY; everything else is BTC."""
    if order_type is OrderType.MARKET and side is Side.BUY:
        yen = (amount_btc * price).to_integral_value(rounding=ROUND_DOWN)
        return Decimal(yen)
    return amount_btc
