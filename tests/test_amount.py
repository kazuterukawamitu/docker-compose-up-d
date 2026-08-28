from decimal import Decimal

import pytest

from bitbank_bot.exceptions import InsufficientFundsError
from bitbank_bot.models import OrderType, Side
from bitbank_bot.orders.amount import (
    buyable_btc,
    market_buy_jpy,
    order_payload_amount,
    quantize_btc,
    quantize_price,
    validate_order_amount,
)


def test_quantize_btc_floors_to_min_step() -> None:
    assert quantize_btc(Decimal("0.00019")) == Decimal("0.0001")
    assert quantize_btc(Decimal("0.00009")) == Decimal("0")


def test_quantize_price_jpy_tick() -> None:
    assert quantize_price(Decimal("123456.9")) == Decimal("123456")


def test_buyable_btc_applies_fee_and_min_size(settings) -> None:
    amount = buyable_btc(Decimal("1000000"), Decimal("10000000"), settings)
    assert amount >= settings.min_order_btc
    assert amount == quantize_btc(amount)


def test_validate_rejects_dust_buy(settings) -> None:
    with pytest.raises(InsufficientFundsError):
        validate_order_amount(
            Side.BUY,
            Decimal("0.0001"),
            Decimal("10000000"),
            jpy_free=Decimal("10"),
            btc_free=Decimal("0"),
            settings=settings,
        )


def test_market_buy_payload_is_jpy(settings) -> None:
    yen = order_payload_amount(
        Side.BUY,
        OrderType.MARKET,
        Decimal("0.01"),
        Decimal("10000000"),
        settings,
    )
    assert yen == Decimal("100000")
    yen_free = market_buy_jpy(Decimal("1000.9"), settings)
    assert yen_free < Decimal("1000")
    assert yen_free == yen_free.to_integral_value()
