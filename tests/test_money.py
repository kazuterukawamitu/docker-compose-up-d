from __future__ import annotations

from decimal import Decimal, InvalidOperation

import pytest

from bitbank_bot.money import D, ensure_decimal, floor_btc, meets_min_amount, to_decimal, truncate


def test_d_parses_exchange_strings() -> None:
    assert D("0.0001") == Decimal("0.0001")
    assert D("10000000") == Decimal("10000000")
    assert D(None) == Decimal("0")
    assert D("") == Decimal("0")
    assert D(10_000_000) == Decimal("10000000")
    assert D(100.5) == Decimal("100.5")


def test_non_finite_float_rejected() -> None:
    with pytest.raises(InvalidOperation):
        D(float("nan"))
    with pytest.raises(InvalidOperation):
        D(float("inf"))


def test_bool_rejected() -> None:
    with pytest.raises(TypeError):
        D(True)


def test_empty_strict() -> None:
    with pytest.raises(ValueError, match="empty"):
        to_decimal("")


def test_ensure_decimal_names_the_field() -> None:
    with pytest.raises(InvalidOperation, match="order_amount"):
        ensure_decimal("", "order_amount")
    with pytest.raises(InvalidOperation, match="bool"):
        ensure_decimal(True, "order_price")
    with pytest.raises(InvalidOperation, match="non-finite"):
        ensure_decimal(Decimal("NaN"), "planned_order_jpy")
    assert ensure_decimal("0.0001", "order_amount") == Decimal("0.0001")


def test_invalid_string() -> None:
    with pytest.raises(InvalidOperation):
        D("not-a-number")


def test_floor_btc_min_lot() -> None:
    assert floor_btc("0.00019") == Decimal("0.0001")
    assert floor_btc("0.00009") == Decimal("0")


def test_truncate_and_min() -> None:
    assert truncate(Decimal("0.00123"), Decimal("0.0001")) == Decimal("0.0012")
    assert meets_min_amount(Decimal("0.0001"), Decimal("0.0001"))
    assert not meets_min_amount(Decimal("0"), Decimal("0.0001"))
