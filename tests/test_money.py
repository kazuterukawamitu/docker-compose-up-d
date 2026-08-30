from decimal import Decimal, InvalidOperation

import pytest

from bitbank_bot.money import D, floor_btc, jpy_tick, meets_min_amount, pct_offset, quantize_price, to_decimal, truncate


def test_decimal_from_str_and_int() -> None:
    assert D("0.0001") == Decimal("0.0001")
    assert D(1) == Decimal("1")
    assert D(None) == Decimal("0")


def test_to_decimal_rejects_float() -> None:
    with pytest.raises(TypeError):
        to_decimal(1.5)


def test_truncate_never_rounds_up() -> None:
    assert truncate(D("0.00019"), D("0.0001")) == D("0.0001")
    assert truncate(D("1.999"), D("1")) == D("1")
    assert truncate(D("0.00009"), D("0.0001")) == D("0")
    assert floor_btc("0.00019") == Decimal("0.0001")


def test_price_tick_one_jpy() -> None:
    assert quantize_price(D("12345678.9"), D("1")) == D("12345678")
    assert jpy_tick("123456.9", side="buy") == Decimal("123456")
    assert jpy_tick("123456.1", side="sell") == Decimal("123457")


def test_min_amount() -> None:
    assert meets_min_amount(D("0.0001"), D("0.0001"))
    assert not meets_min_amount(D("0.00009"), D("0.0001"))
    assert not meets_min_amount(D("0"), D("0.0001"))


def test_pct_offset_tp() -> None:
    assert pct_offset(D("100"), D("0.03")) == D("103")
    assert pct_offset(D("100"), D("0.08")) == D("108")


def test_invalid_decimal() -> None:
    with pytest.raises(InvalidOperation):
        D("not-a-number")
