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


def test_daily_pnl_floor_default_150(tmp_path) -> None:
    c = cfg(
        daily_pnl_floor=D("150"),
        max_daily_loss_jpy=D("0"),
        kill_switch=False,
        kill_switch_path=str(tmp_path / "KILL"),
    )
    risk = RiskManager(c)
    assert not risk.killed
    risk.record_realized_pnl(D("-150"))
    assert risk.killed


def test_kill_file_trips(tmp_path) -> None:
    kill = tmp_path / "KILL"
    kill.write_text("stop\n")
    c = cfg(kill_switch=False, kill_switch_path=str(kill))
    risk = RiskManager(c)
    assert risk.killed
    decision = risk.check_buy(D("0"), D("0.1"))
    assert not decision.allowed
    assert decision.reason == "kill_switch"
