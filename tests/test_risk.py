from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from bitbank_bot.risk import RiskManager
from tests.helpers import cfg


def test_daily_pnl_floor_blocks_buy_not_sell(tmp_path: Path) -> None:
    c = cfg(kill_switch_path=str(tmp_path / "KILL"), daily_pnl_floor=Decimal("150"))
    r = RiskManager(c)
    r.record_realized_pnl(Decimal("-200"))
    buy = r.check_buy(Decimal("0"), Decimal("0.01"))
    assert not buy.allowed
    assert buy.reason == "daily_pnl_floor"
    sell = r.check_sell(Decimal("0.01"))
    assert sell.allowed


def test_kill_file_blocks(tmp_path: Path) -> None:
    kill = tmp_path / "KILL"
    kill.write_text("1")
    c = cfg(kill_switch_path=str(kill), daily_pnl_floor=Decimal("0"))
    r = RiskManager(c)
    buy = r.check_buy(Decimal("0"), Decimal("0.01"))
    assert not buy.allowed
    assert buy.reason == "kill_switch"
    sell = r.check_sell(Decimal("0.01"))
    assert not sell.allowed
    assert sell.reason == "kill_switch"


def test_max_position() -> None:
    c = cfg(max_position_btc=Decimal("0.01"), daily_pnl_floor=Decimal("0"))
    r = RiskManager(c)
    buy = r.check_buy(Decimal("0.01"), Decimal("0.01"))
    assert not buy.allowed
    assert buy.reason == "max_position"


def test_check_stale_blocks_old_ticker() -> None:
    c = cfg(stale_ws_sec=60)
    r = RiskManager(c)
    assert r.check_stale(10).allowed
    blocked = r.check_stale(61)
    assert not blocked.allowed
    assert blocked.reason == "stale_data"


def test_daily_halt_resets_next_jst_day() -> None:
    c = cfg(daily_pnl_floor=Decimal("150"))
    r = RiskManager(c, daily_pnl=Decimal("-200"), daily_pnl_date="2000-01-01")
    r.set_as_of(1_700_000_000_000)
    buy = r.check_buy(Decimal("0"), Decimal("0.01"))
    assert buy.allowed
