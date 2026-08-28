from bitbank_bot.amounts import plan_buy, plan_sell
from bitbank_bot.money import D
from bitbank_bot.risk import RiskManager

from helpers import cfg


def test_jpy_greater_than_target() -> None:
    c = cfg()
    risk = RiskManager(c)
    plan = plan_buy(
        available_jpy=D("100000"),
        available_btc=D("0"),
        price=D("10000"),
        cfg=c,
        risk=risk,
        target_jpy=D("10000"),
    )
    assert plan.ok
    assert plan.target_jpy == D("10000")
    assert plan.planned_order_jpy <= plan.target_jpy
    assert plan.planned_order_jpy == plan.amount * plan.price
    assert plan.actual_execution_jpy is None


def test_jpy_less_than_target_caps_to_balance() -> None:
    c = cfg()
    risk = RiskManager(c)
    plan = plan_buy(
        available_jpy=D("5000"),
        available_btc=D("0"),
        price=D("10000"),
        cfg=c,
        risk=risk,
        target_jpy=D("100000"),
    )
    assert plan.ok
    assert plan.planned_order_jpy <= D("5000") * c.max_balance_usage
    assert plan.planned_order_jpy < plan.target_jpy


def test_sell_capped_by_btc() -> None:
    c = cfg()
    risk = RiskManager(c)
    plan = plan_sell(
        available_jpy=D("0"),
        available_btc=D("0.01234"),
        price=D("10000000"),
        cfg=c,
        risk=risk,
    )
    assert plan.ok
    assert plan.amount <= D("0.01234")
    assert plan.amount == D("0.0123")


def test_insufficient_jpy() -> None:
    c = cfg()
    risk = RiskManager(c)
    plan = plan_buy(
        available_jpy=D("1"),
        available_btc=D("0"),
        price=D("10000000"),
        cfg=c,
        risk=risk,
    )
    assert not plan.ok
    assert plan.reason in {"insufficient", "below_min_amount"}
    assert plan.amount == D("0")


def test_below_min_sell() -> None:
    c = cfg()
    risk = RiskManager(c)
    plan = plan_sell(
        available_jpy=D("0"),
        available_btc=D("0.00005"),
        price=D("10000000"),
        cfg=c,
        risk=risk,
    )
    assert not plan.ok
    assert plan.reason in {"insufficient", "below_min_amount"}
