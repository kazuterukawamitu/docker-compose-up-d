from __future__ import annotations

from decimal import Decimal

from bitbank_bot.buy_funnel import buy_setup_clauses, measure_buy_funnel, setup_fired
from bitbank_bot.indicators import Trend
from bitbank_bot.money import D
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import MarketSnapshot, Position, Strategy
from tests.helpers import cfg


def _snap(**overrides: object) -> MarketSnapshot:
    base = dict(
        index=10,
        timestamp_ms=10,
        close=D("100"),
        prev_close=D("100"),
        ma=D("100"),
        prev_ma=D("100"),
        short_ma=D("100"),
        prev_short_ma=D("100"),
        long_ma=D("100"),
        prev_long_ma=D("100"),
        ma_trend=Trend.FLAT,
        prev_ma_trend=Trend.FLAT,
        crossed_up=False,
        crossed_down=False,
        golden_cross=False,
        dead_cross=False,
        cross_price=None,
    )
    base.update(overrides)
    return MarketSnapshot(**base)  # type: ignore[arg-type]


def test_setup_and_filters_are_not_dropped() -> None:
    c = cfg()
    strat = Strategy(c)
    snap = _snap(
        prev_ma_trend=Trend.DOWN,
        ma_trend=Trend.UP,
        crossed_up=False,
    )
    clauses = buy_setup_clauses(snap, strat)
    fired, name = setup_fired(clauses)
    assert fired is False
    assert name == "no_buy_setup"
    assert clauses["BUY1"]["prev_ma_down"] is True
    assert clauses["BUY1"]["ma_flat_or_up"] is True
    assert clauses["BUY1"]["crossed_up"] is False


def test_buy1_requires_all_three_and_clauses() -> None:
    c = cfg()
    strat = Strategy(c)
    complete = _snap(
        prev_ma_trend=Trend.DOWN,
        ma_trend=Trend.FLAT,
        crossed_up=True,
    )
    fired, name = setup_fired(buy_setup_clauses(complete, strat))
    assert fired is True
    assert name == "BUY1"
    missing_cross = _snap(
        prev_ma_trend=Trend.DOWN,
        ma_trend=Trend.FLAT,
        crossed_up=False,
    )
    fired, name = setup_fired(buy_setup_clauses(missing_cross, strat))
    assert fired is False


def test_funnel_reports_each_gate(tmp_path) -> None:
    c = cfg(kill_switch_path=str(tmp_path / "missing-KILL"))
    strat = Strategy(c)
    snap = _snap()
    report = measure_buy_funnel(
        snap=snap,
        strategy=strat,
        cfg=c,
        risk=RiskManager(c),
        position=None,
        pending=False,
        htf_allow=True,
        htf_reason="htf_ok",
        ws_stale=False,
        executable=True,
        available_jpy=Decimal("100000"),
        available_btc=Decimal("0"),
        price=Decimal("10000000"),
        ky_veto=False,
        ky_reason="ok",
    )
    names = [gate.name for gate in report.gates]
    assert names == [
        "flat",
        "pending",
        "setup",
        "htf",
        "websocket",
        "executable",
        "risk",
        "size",
        "ky",
    ]
    assert report.gate("setup") is not None
    assert report.gate("setup").passed is False
    assert report.gate("size").passed is True
    assert report.open is False
    assert report.first_fail == "no_buy_setup"


def test_funnel_in_position_fails_flat_gate() -> None:
    c = cfg()
    pos = Position(
        amount=D("0.001"),
        average_price=D("10000000"),
        tp_pct=D("0.03"),
        entry_candle_index=1,
        entry_candle_ts=1,
        actual_execution_jpy=D("10000"),
        kind="BUY1",
    )
    report = measure_buy_funnel(
        snap=_snap(),
        strategy=Strategy(c),
        cfg=c,
        risk=RiskManager(c),
        position=pos,
        pending=True,
        htf_allow=False,
        htf_reason="htf_downtrend",
        ws_stale=True,
        executable=False,
        available_jpy=Decimal("100000"),
        available_btc=Decimal("0.001"),
        price=Decimal("10000000"),
        ky_veto=True,
        ky_reason="ky_veto",
    )
    assert report.gate("flat").passed is False
    assert report.gate("pending").passed is False
    assert report.gate("htf").passed is False
    assert report.gate("websocket").passed is False
    assert report.gate("executable").passed is False
    assert report.gate("ky").passed is False
    assert report.first_fail == "in_position"


def test_buy4_same_bar_dip_and_rise_is_not_complete() -> None:
    c = cfg()
    strat = Strategy(c)
    snap = _snap(
        close=D("94"),
        prev_close=D("93"),
        ma=D("100"),
        prev_ma=D("100.2"),
        ma_trend=Trend.DOWN,
        prev_ma_trend=Trend.DOWN,
    )
    strat.observe(snap)
    assert strat._buy4 is False
    assert strat.buy4.phase == "dipped"
    clauses = buy_setup_clauses(snap, strat)
    fired, name = setup_fired(clauses)
    assert fired is False
    assert name == "no_buy_setup"
    assert clauses["BUY4"]["ma_downtrend"] is True
    assert clauses["BUY4"]["held_dip"] is True
    assert clauses["BUY4"]["bounce_after_dip"] is False


def test_buy4_funnel_fires_only_on_later_bar_after_dip() -> None:
    c = cfg()
    strat = Strategy(c)
    dip = _snap(
        close=D("94"),
        prev_close=D("100"),
        ma=D("100"),
        prev_ma=D("100.2"),
        ma_trend=Trend.DOWN,
        prev_ma_trend=Trend.DOWN,
    )
    strat.observe(dip)
    assert strat._buy4 is False
    bounce = _snap(
        index=11,
        timestamp_ms=11,
        close=D("96"),
        prev_close=D("94"),
        ma=D("100"),
        prev_ma=D("100.1"),
        ma_trend=Trend.DOWN,
        prev_ma_trend=Trend.DOWN,
    )
    strat.observe(bounce)
    assert strat._buy4 is True
    fired, name = setup_fired(buy_setup_clauses(bounce, strat))
    assert fired is True
    assert name == "BUY4"


def test_funnel_size_error_matches_execute_path_failure() -> None:
    c = cfg()
    report = measure_buy_funnel(
        snap=_snap(),
        strategy=Strategy(c),
        cfg=c,
        risk=RiskManager(c),
        position=None,
        pending=False,
        htf_allow=True,
        htf_reason="htf_ok",
        ws_stale=False,
        executable=True,
        available_jpy=Decimal("100000"),
        available_btc=Decimal("0"),
        price=Decimal("10000000"),
        ky_veto=False,
        ky_reason="ok",
        size_error="balance_fetch_failed",
    )
    assert report.gate("size") is not None
    assert report.gate("size").passed is False
    assert report.gate("size").reason == "balance_fetch_failed"
