from decimal import Decimal

from bitbank_bot.models import Position, Side, Signal, Ticker
from bitbank_bot.risk.manager import RiskManager


def _ticker(price: str) -> Ticker:
    px = Decimal(price)
    return Ticker(
        pair="btc_jpy",
        last=px,
        bid=px,
        ask=px,
        high=px,
        low=px,
        volume=Decimal("1"),
        timestamp_ms=1,
    )


def test_stop_loss_triggers(settings) -> None:
    risk = RiskManager(settings)
    pos = Position(pair="btc_jpy", amount_btc=Decimal("0.01"), entry_price=Decimal("10000000"))
    pos.high_water = Decimal("10000000")
    signal = risk.protective_exit(pos, Decimal("9600000"))
    assert signal is not None
    assert signal.side is Side.SELL
    assert "stop-loss" in signal.reason


def test_strategy_take_profit(settings) -> None:
    risk = RiskManager(settings)
    pos = Position(
        pair="btc_jpy",
        amount_btc=Decimal("0.01"),
        entry_price=Decimal("100"),
        take_profit_pct=Decimal("0.03"),
        high_water=Decimal("100"),
    )
    signal = risk.protective_exit(pos, Decimal("104"))
    assert signal is not None
    assert "strategy TP" in signal.reason


def test_blocks_buy_when_already_long(settings) -> None:
    risk = RiskManager(settings)
    pos = Position(pair="btc_jpy", amount_btc=Decimal("0.01"), entry_price=Decimal("100"))
    decision = risk.approve(
        Signal(Side.BUY, "test", take_profit_pct=Decimal("0.03")),
        pos,
        _ticker("100"),
        Decimal("1000000"),
        Decimal("0.01"),
    )
    assert decision.allowed is False


def test_max_position_cap(settings) -> None:
    risk = RiskManager(settings)
    assert risk.cap_buy_amount(Decimal("2"), Decimal("0.2")) == Decimal("0.8")
