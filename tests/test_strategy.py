from bitbank_bot.indicators import Trend
from bitbank_bot.money import D
from bitbank_bot.strategy import Strategy

from helpers import cfg, position, snap


def test_buy1_ma_leaves_downtrend_and_price_crosses_up() -> None:
    s = Strategy(cfg())
    sig = s.evaluate(
        snap(
            prev_ma_trend=Trend.DOWN,
            ma_trend=Trend.UP,
            crossed_up=True,
            cross_price=D("100"),
        ),
        None,
    )
    assert sig.kind == "BUY1"
    assert sig.side == "buy"
    assert sig.tp_pct == D("0.03")
    assert sig.crossover_price_bp == D("1")
    assert sig.reason


def test_buy2_golden_cross_vs_not() -> None:
    s = Strategy(cfg())
    golden = s.evaluate(
        snap(ma_trend=Trend.UP, crossed_down=True, golden_cross=True),
        None,
    )
    assert golden.kind == "BUY2"
    assert golden.tp_pct == D("0.08")
    s2 = Strategy(cfg())
    plain = s2.evaluate(
        snap(ma_trend=Trend.UP, crossed_down=True, golden_cross=False),
        None,
    )
    assert plain.kind == "BUY2"
    assert plain.tp_pct == D("0.05")
    assert not plain.golden_cross


def test_buy3_state_machine_not_single_candle() -> None:
    s = Strategy(cfg())
    first = s.evaluate(snap(close=D("106"), ma=D("100")), None)
    assert first.kind == "HOLD"
    second = s.evaluate(snap(close=D("105"), ma=D("100")), None)
    assert second.kind == "HOLD"
    third = s.evaluate(snap(close=D("105.5"), ma=D("100")), None)
    assert third.kind == "BUY3"
    assert third.tp_pct == D("0.04")


def test_buy3_resets_if_price_reaches_ma() -> None:
    s = Strategy(cfg())
    s.evaluate(snap(close=D("106"), ma=D("100")), None)
    s.evaluate(snap(close=D("100"), ma=D("100")), None)
    sig = s.evaluate(snap(close=D("101"), ma=D("100")), None)
    assert sig.kind == "HOLD"


def test_buy4_downtrend_dip_then_rise() -> None:
    s = Strategy(cfg())
    first = s.evaluate(snap(close=D("94"), ma=D("100"), ma_trend=Trend.DOWN), None)
    assert first.kind == "HOLD"
    second = s.evaluate(snap(close=D("95"), ma=D("100"), ma_trend=Trend.DOWN), None)
    assert second.kind == "BUY4"
    assert second.tp_pct == D("0.05")


def test_sell1_extended_then_turns_down() -> None:
    s = Strategy(cfg())
    pos = position()
    s.evaluate(snap(index=4, close=D("105"), ma=D("100")), pos)
    sig = s.evaluate(snap(index=5, close=D("104"), ma=D("100")), pos)
    assert sig.kind == "SELL1"
    assert sig.side == "sell"


def test_sell2_fall_cross_continue() -> None:
    s = Strategy(cfg())
    pos = position()
    s.evaluate(snap(index=4, close=D("99"), prev_close=D("100"), crossed_down=False), pos)
    s.evaluate(snap(index=5, close=D("98"), prev_close=D("99"), crossed_down=True), pos)
    sig = s.evaluate(
        snap(index=6, close=D("97"), prev_close=D("98"), crossed_down=False), pos
    )
    assert sig.kind == "SELL2"


def test_sell3_downtrend_cross_up() -> None:
    s = Strategy(cfg())
    sig = s.evaluate(
        snap(index=8, ma_trend=Trend.DOWN, crossed_up=True, cross_price=D("100")),
        position(),
    )
    assert sig.kind == "SELL3"


def test_sell4_failed_recovery() -> None:
    s = Strategy(cfg())
    pos = position()
    s.evaluate(snap(index=4, close=D("95"), ma=D("100")), pos)
    s.evaluate(snap(index=5, close=D("96"), ma=D("100")), pos)
    sig = s.evaluate(snap(index=6, close=D("95.5"), ma=D("100")), pos)
    assert sig.kind == "SELL4"


def test_same_candle_sell_blocked() -> None:
    s = Strategy(cfg())
    pos = position(entry_candle_index=5)
    s.observe(snap(index=5, close=D("105"), ma=D("100")))
    sig = s.evaluate(snap(index=5, close=D("104"), ma=D("100")), pos)
    assert sig.kind != "SELL1"
    assert sig.side != "sell"


def test_take_profit_uses_actual_average() -> None:
    s = Strategy(cfg())
    pos = position(average_price=D("200"), tp_pct=D("0.03"))
    hold = s.evaluate(snap(index=3, close=D("205"), ma=D("200")), pos)
    assert hold.kind == "HOLD"
    tp = s.evaluate(snap(index=4, close=D("206"), ma=D("200")), pos)
    assert tp.kind == "TP"
    assert tp.side == "sell"


def test_sell_priority_over_tp() -> None:
    s = Strategy(cfg())
    pos = position(average_price=D("100"), tp_pct=D("0.03"))
    s.evaluate(snap(index=4, close=D("105"), ma=D("100")), pos)
    sig = s.evaluate(snap(index=5, close=D("104"), ma=D("100")), pos)
    assert sig.kind == "SELL1"


def test_no_buy_when_in_position() -> None:
    s = Strategy(cfg())
    sig = s.evaluate(
        snap(prev_ma_trend=Trend.DOWN, ma_trend=Trend.UP, crossed_up=True),
        position(entry_candle_index=1),
    )
    assert sig.kind != "BUY1"


def test_hold_always_has_reason() -> None:
    s = Strategy(cfg())
    sig = s.evaluate(snap(), None)
    assert sig.kind == "HOLD"
    assert sig.reason


def test_wiki_golden_off_by_default() -> None:
    s = Strategy(cfg())
    sig = s.evaluate(snap(golden_cross=True), None)
    assert sig.kind == "HOLD"


def test_wiki_golden_and_dead_when_enabled() -> None:
    s = Strategy(cfg(wiki_cross_rules=True))
    buy = s.evaluate(snap(golden_cross=True), None)
    assert buy.kind == "WIKI_GOLDEN"
    assert buy.side == "buy"
    sell = s.evaluate(snap(index=8, dead_cross=True), position())
    assert sell.kind == "WIKI_DEAD"
    assert sell.side == "sell"
