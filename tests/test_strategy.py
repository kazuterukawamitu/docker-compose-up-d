from __future__ import annotations

from decimal import Decimal

from bitbank_bot.indicators import Trend, interpolate_crossover, ma_trend, sma
from bitbank_bot.money import D
from bitbank_bot.strategy import Position, Strategy, build_snapshots
from tests.helpers import cfg


def test_sma_period() -> None:
    values = [D(i) for i in range(1, 6)]
    out = sma(values, 3)
    assert out[1] is None
    assert out[2] == D("2")
    assert out[4] == D("4")


def test_ma_trend_threshold() -> None:
    assert ma_trend(D("100.1"), D("100"), D("0.0005")) == Trend.UP
    assert ma_trend(D("99.9"), D("100"), D("0.0005")) == Trend.DOWN
    assert ma_trend(D("100.01"), D("100"), D("0.0005")) == Trend.FLAT


def test_interpolate_crossover() -> None:
    price = interpolate_crossover(D("99"), D("100"), D("101"), D("100"))
    assert price is not None
    assert D("99") < price < D("101")


def _snaps_from_closes(closes: list[Decimal]):
    c = cfg(ma_period=3, short_ma_period=3, long_ma_period=5, ma_slope_threshold=D("0.0001"))
    stamps = list(range(len(closes)))
    return build_snapshots(closes, stamps, c), c


def test_buy1_after_downtrend_cross_up() -> None:
    closes = [D(200 - i) for i in range(25)]
    closes.extend([D("176"), D("177")])
    snaps, c = _snaps_from_closes(closes)
    strat = Strategy(c)
    last_buy = None
    for snap in snaps:
        sig = strat.evaluate(snap, None)
        if sig.kind == "BUY1":
            last_buy = sig
    assert last_buy is not None
    assert last_buy.side == "buy"
    assert last_buy.tp_pct == c.buy1_tp


def test_hold_in_position_same_candle() -> None:
    c = cfg(ma_period=3, short_ma_period=3, long_ma_period=5)
    closes = [D(100)] * 10
    snaps = build_snapshots(closes, list(range(10)), c)
    pos = Position(
        amount=D("0.01"),
        average_price=D("100"),
        tp_pct=D("0.03"),
        entry_candle_index=snaps[-1].index,
        entry_candle_ts=snaps[-1].timestamp_ms,
        actual_execution_jpy=D("1000"),
        kind="BUY1",
    )
    sig = Strategy(c).evaluate(snaps[-1], pos)
    assert sig.kind == "HOLD"
    assert sig.reason == "same_entry_candle_no_sell"


def test_take_profit_sells() -> None:
    c = cfg(ma_period=3, short_ma_period=3, long_ma_period=5)
    closes = [D("100")] * 8 + [D("104")]
    snaps = build_snapshots(closes, list(range(len(closes))), c)
    pos = Position(
        amount=D("0.01"),
        average_price=D("100"),
        tp_pct=D("0.03"),
        entry_candle_index=0,
        entry_candle_ts=0,
        actual_execution_jpy=D("1000"),
        kind="BUY1",
    )
    strat = Strategy(c)
    for snap in snaps[:-1]:
        strat.observe(snap)
    sig = strat.evaluate(snaps[-1], pos)
    assert sig.kind == "TP"
    assert sig.side == "sell"


def test_hold_requires_reason() -> None:
    from bitbank_bot.strategy import Signal

    assert Signal.hold("no_buy_setup").reason == "no_buy_setup"


def test_sell3_on_upcross_in_downtrend() -> None:
    # Bounce just through a still-falling SMA so trend stays DOWN (a large
    # bounce would flip SMA to UP and would not be SELL3).
    c = cfg(ma_period=5, short_ma_period=5, long_ma_period=8, ma_slope_threshold=D("0.0001"))
    closes = [D(200 - i) for i in range(30)] + [D("168"), D("172")]
    snaps = build_snapshots(closes, list(range(len(closes))), c)
    pos = Position(
        amount=D("0.01"),
        average_price=D("180"),
        tp_pct=D("0.03"),
        entry_candle_index=0,
        entry_candle_ts=0,
        actual_execution_jpy=D("1800"),
        kind="BUY4",
    )
    strat = Strategy(c)
    last_sell = None
    for snap in snaps:
        sig = strat.evaluate(snap, pos if snap.index != 0 else None)
        if sig.kind == "SELL3":
            last_sell = sig
    assert last_sell is not None
    assert last_sell.side == "sell"
