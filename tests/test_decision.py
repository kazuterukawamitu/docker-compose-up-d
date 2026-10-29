from decimal import Decimal

from bitbank_bot.decision import (
    buy_block_reason,
    price_exit,
    required_edge,
    shannon_entropy,
    unrealized_jpy,
)
from bitbank_bot.money import D
from bitbank_bot.strategy import Position


def _pos(**overrides: object) -> Position:
    base = dict(
        amount=D("0.001"),
        average_price=D("10000000"),
        tp_pct=D("0.03"),
        entry_candle_index=1,
        entry_candle_ts=1,
        actual_execution_jpy=D("10000"),
        kind="BUY1",
        fee_jpy=D("12"),
    )
    base.update(overrides)
    return Position(**base)  # type: ignore[arg-type]


def test_entropy_is_zero_for_a_one_sided_move() -> None:
    closes = [D(10_000_000) - D(i) * D(1000) for i in range(12)]
    assert shannon_entropy(closes) == Decimal("0")


def test_entropy_rises_when_returns_change_sign() -> None:
    closes = []
    price = D("10000000")
    for i in range(16):
        price = price + D("300000") if i % 2 == 0 else price - D("300000")
        closes.append(price)
    assert shannon_entropy(closes) > Decimal("0")


def test_buy_blocked_when_take_profit_cannot_pay_fees() -> None:
    need = required_edge(D("0.0012"), D("0"))
    assert need == D("0.0024")
    assert buy_block_reason(D("0.002"), D("0.0012"), D("0")) == "fee_exceeds_edge"
    assert buy_block_reason(D("0.03"), D("0.0012"), D("0")) is None


def test_stop_uses_live_mark_not_the_candle() -> None:
    signal = price_exit(
        _pos(),
        D("9700000"),
        stop_loss_pct=D("0.02"),
        taker_fee_rate=D("0.0012"),
    )
    assert signal is not None
    assert signal.kind == "STOP"
    assert signal.side == "sell"


def test_take_profit_waits_until_fees_are_covered() -> None:
    rich = _pos(fee_jpy=D("5000"))
    blocked = price_exit(
        rich,
        D("10300000"),
        stop_loss_pct=D("0.02"),
        taker_fee_rate=D("0.0012"),
    )
    assert blocked is None
    assert unrealized_jpy(rich, D("10300000"), D("0.0012")) < 0
    allowed = price_exit(
        _pos(),
        D("10300000"),
        stop_loss_pct=D("0.02"),
        taker_fee_rate=D("0.0012"),
    )
    assert allowed is not None
    assert allowed.kind == "TP"


def test_daily_loss_flattens_without_disabling_a_later_buy_rule() -> None:
    signal = price_exit(
        _pos(),
        D("10000000"),
        stop_loss_pct=D("0"),
        taker_fee_rate=D("0"),
        max_daily_loss_jpy=D("1000"),
        daily_pnl=D("-1000"),
    )
    assert signal is not None
    assert signal.reason.startswith("daily_pnl_flatten")
