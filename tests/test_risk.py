from bitbank_bot.money import D
from bitbank_bot.risk import RiskManager

from helpers import cfg


def test_kill_switch_blocks_buy() -> None:
    c = cfg(kill_switch=True)
    risk = RiskManager(c)
    decision = risk.check_buy(D("0"), D("0.1"))
    assert not decision.allowed
    assert decision.killed
    assert decision.reason == "kill_switch"


def test_max_position_caps_buy() -> None:
    c = cfg(max_position_btc=D("0.2"))
    risk = RiskManager(c)
    decision = risk.check_buy(D("0.15"), D("0.2"))
    assert decision.allowed
    assert decision.capped_btc == D("0.05")


def test_max_daily_loss_trips_kill() -> None:
    c = cfg(max_daily_loss_jpy=D("1000"), kill_switch=False)
    risk = RiskManager(c)
    assert not risk.killed
    risk.record_realized_pnl(D("-1000"))
    assert risk.killed
    decision = risk.check_buy(D("0"), D("0.1"))
    assert not decision.allowed
