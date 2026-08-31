from datetime import date

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


def test_max_daily_loss_trips_halt_not_kill_switch() -> None:
    c = cfg(max_daily_loss_jpy=D("1000"), daily_pnl_floor=D("0"), kill_switch=False)
    risk = RiskManager(c)
    assert not risk.killed
    risk.record_realized_pnl(D("-1000"))
    assert risk.killed
    assert risk.halt_reason() == "max_daily_loss"
    decision = risk.check_buy(D("0"), D("0.1"))
    assert not decision.allowed
    assert decision.reason == "max_daily_loss"
    assert decision.reason != "kill_switch"


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
    decision = risk.check_buy(D("0"), D("0.1"))
    assert not decision.allowed
    assert decision.reason == "daily_pnl_floor"


def test_daily_halt_resets_next_jst_day(tmp_path) -> None:
    c = cfg(
        daily_pnl_floor=D("150"),
        max_daily_loss_jpy=D("0"),
        kill_switch=False,
        kill_switch_path=str(tmp_path / "KILL"),
    )
    risk = RiskManager(c)
    risk.set_as_of_date(date(2026, 8, 30))
    risk.record_realized_pnl(D("-200"))
    assert risk.halt_reason() == "daily_pnl_floor"
    risk.set_as_of_date(date(2026, 8, 31))
    assert risk.halt_reason() is None
    decision = risk.check_buy(D("0"), D("0.1"))
    assert decision.allowed
    assert decision.reason == "ok"


def test_kill_file_trips(tmp_path) -> None:
    kill = tmp_path / "KILL"
    kill.write_text("stop\n")
    c = cfg(kill_switch=False, kill_switch_path=str(kill))
    risk = RiskManager(c)
    assert risk.killed
    decision = risk.check_buy(D("0"), D("0.1"))
    assert not decision.allowed
    assert decision.reason == "kill_switch"


def test_kill_file_removed_unblocks(tmp_path) -> None:
    kill = tmp_path / "KILL"
    kill.write_text("stop\n")
    c = cfg(kill_switch=False, kill_switch_path=str(kill))
    risk = RiskManager(c)
    assert risk.check_buy(D("0"), D("0.1")).reason == "kill_switch"
    kill.unlink()
    decision = risk.check_buy(D("0"), D("0.1"))
    assert decision.allowed
    assert decision.reason == "ok"
    assert not risk.operator_killed


def test_open_allows_buy_when_kill_switch_off(tmp_path) -> None:
    c = cfg(kill_switch=False, kill_switch_path=str(tmp_path / "missing-KILL"))
    risk = RiskManager(c, killed=False)
    decision = risk.check_buy(D("0"), D("0.1"))
    assert decision.allowed
    assert decision.reason == "ok"
    assert decision.capped_btc == D("0.1")


def test_circuit_breaker_after_consecutive_errors() -> None:
    c = cfg(circuit_breaker_errors=3, daily_pnl_floor=D("0"), kill_switch=False)
    risk = RiskManager(c)
    risk.note_api_error()
    risk.note_api_error()
    assert risk.check_buy(D("0"), D("0.1")).allowed
    risk.note_api_error()
    decision = risk.check_buy(D("0"), D("0.1"))
    assert not decision.allowed
    assert decision.reason == "circuit_breaker"
    sell = risk.check_sell(D("0.1"))
    assert not sell.allowed
    assert sell.reason == "circuit_breaker"


def test_auth_failure_blocks_all_orders() -> None:
    c = cfg(daily_pnl_floor=D("0"), kill_switch=False)
    risk = RiskManager(c)
    risk.note_auth_failure()
    buy = risk.check_buy(D("0"), D("0.1"))
    assert not buy.allowed
    assert buy.reason == "auth_failure"
    sell = risk.check_sell(D("0.1"))
    assert not sell.allowed
    assert sell.reason == "auth_failure"


def test_max_drawdown_blocks_buy_not_sell() -> None:
    c = cfg(
        max_drawdown_jpy=D("150"),
        daily_pnl_floor=D("0"),
        kill_switch=False,
        kill_switch_path="/tmp/bitbank-bot-tests-no-kill-file",
    )
    risk = RiskManager(c)
    risk.update_equity(D("1000"), D("0"), D("1"))
    risk.update_equity(D("800"), D("0"), D("1"))
    assert risk.halt_reason() == "max_drawdown"
    buy = risk.check_buy(D("0"), D("0.1"))
    assert not buy.allowed
    sell = risk.check_sell(D("0.1"))
    assert sell.allowed
