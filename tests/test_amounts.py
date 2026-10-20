from __future__ import annotations

from decimal import Decimal

from bitbank_bot.amounts import PositionSizer, plan_buy, plan_sell
from tests.helpers import cfg, risk


def test_buy_from_free_jpy_floors_to_lot() -> None:
    c = cfg()
    r = risk(c)
    plan = plan_buy(
        available_jpy=Decimal("100000"),
        available_btc=Decimal("0"),
        price=Decimal("10000000"),
        cfg=c,
        risk=r,
    )
    assert plan.ok
    assert plan.amount == Decimal("0.001")
    assert plan.amount_value == 1
    assert plan.unit_btc == Decimal("0.001")
    assert plan.max_buyable_units == 9
    assert plan.target_jpy > 0
    assert plan.planned_order_jpy == plan.amount * plan.price
    assert plan.actual_execution_jpy is None


def test_max_buyable_is_integer_units_not_full_cash() -> None:
    c = cfg(amount_value=0)
    plan = plan_buy(
        available_jpy=Decimal("100000"),
        available_btc=Decimal("0"),
        price=Decimal("10000000"),
        cfg=c,
        risk=risk(c),
    )
    assert plan.ok
    assert plan.amount == Decimal("0.009")
    assert plan.amount_value == 9
    assert plan.max_buyable_units == 9
    full_cash = Decimal("100000") / Decimal("10000000")
    assert plan.amount < full_cash
    assert plan.planned_order_jpy < Decimal("100000") * c.max_balance_usage


def test_amount_value_clamped_by_max_order() -> None:
    c = cfg(amount_value=100, max_order_btc=Decimal("0.003"))
    plan = plan_buy(
        available_jpy=Decimal("1000000"),
        available_btc=Decimal("0"),
        price=Decimal("10000000"),
        cfg=c,
        risk=risk(c),
    )
    assert plan.ok
    assert plan.amount == Decimal("0.003")
    assert plan.amount_value == 3


def test_buy_insufficient_jpy() -> None:
    c = cfg()
    plan = plan_buy(
        available_jpy=Decimal("50"),
        available_btc=Decimal("0"),
        price=Decimal("10000000"),
        cfg=c,
        risk=risk(c),
    )
    assert not plan.ok
    assert plan.amount == Decimal("0")
    assert plan.reason == "insufficient"


def test_buy_below_min_rejected() -> None:
    c = cfg(min_amount_btc=Decimal("0.01"))
    plan = plan_buy(
        available_jpy=Decimal("100000"),
        available_btc=Decimal("0"),
        price=Decimal("10000000"),
        cfg=c,
        risk=risk(c),
    )
    assert not plan.ok
    assert plan.amount == Decimal("0")
    assert plan.reason == "below_min_amount"


def test_buy_invalid_price() -> None:
    c = cfg()
    plan = plan_buy(
        available_jpy=Decimal("100000"),
        available_btc=Decimal("0"),
        price=Decimal("0"),
        cfg=c,
        risk=risk(c),
    )
    assert not plan.ok
    assert plan.reason == "invalid_price"


def test_sell_flattens_free_btc() -> None:
    c = cfg()
    plan = plan_sell(
        available_jpy=Decimal("0"),
        available_btc=Decimal("0.01234"),
        price=Decimal("10000000"),
        cfg=c,
        risk=risk(c),
    )
    assert plan.ok
    assert plan.amount == Decimal("0.0123")


def test_sell_flattens_min_lot_dust() -> None:
    c = cfg()
    plan = plan_sell(
        available_jpy=Decimal("0"),
        available_btc=Decimal("0.001"),
        price=Decimal("10000000"),
        cfg=c,
        risk=risk(c),
    )
    assert plan.ok
    assert plan.amount == Decimal("0.001")


def test_sizer_class_matches_functions() -> None:
    c = cfg()
    sizer = PositionSizer(c, risk(c))
    a = sizer.plan_buy(
        available_jpy=Decimal("200000"),
        available_btc=Decimal("0"),
        price=Decimal("8000000"),
    )
    b = plan_buy(
        available_jpy=Decimal("200000"),
        available_btc=Decimal("0"),
        price=Decimal("8000000"),
        cfg=c,
        risk=risk(c),
    )
    assert a.amount == b.amount
    assert a.ok == b.ok


def test_string_balances_from_api() -> None:
    c = cfg()
    plan = plan_buy(
        available_jpy="50000",  # type: ignore[arg-type]
        available_btc="0",  # type: ignore[arg-type]
        price="10000000",  # type: ignore[arg-type]
        cfg=c,
        risk=risk(c),
    )
    assert plan.ok
    assert plan.amount >= Decimal("0.0001")
