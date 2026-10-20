from __future__ import annotations

from decimal import Decimal

from bitbank_bot.indicators import (
    close_returns,
    daily_pnl_score,
    entropy_regime,
    granville_pullback_score,
    paired_indicator_scores,
    realtime_daily_pnl,
    shannon_entropy,
)
from bitbank_bot.money import D
from bitbank_bot.strategy import Strategy, build_snapshots
from tests.helpers import cfg


def test_close_returns_no_look_ahead() -> None:
    known = [D("100"), D("102"), D("101")]
    future = [D("50")]
    now = close_returns(known)
    later = close_returns(known + future)
    assert now == [D("0.02"), D("-1") / D("102")]
    assert later[-1] == (D("50") - D("101")) / D("101")
    assert later[-1] not in now


def test_shannon_entropy_zero_when_returns_identical() -> None:
    returns = [D("0.01")] * 16
    assert shannon_entropy(returns, bins=8) == D("0")


def test_shannon_entropy_high_when_spread_across_bins() -> None:
    returns = [D(str((i - 7) / 100)) for i in range(16)]
    entropy = shannon_entropy(returns, bins=8)
    assert entropy > D("0.70")
    assert entropy <= D("1")
    assert entropy_regime(entropy) == "CHOP"


def test_high_entropy_is_not_a_buy_signal() -> None:
    closes = []
    price = D("10000")
    for i in range(40):
        step = D("80") if i % 2 == 0 else D("-75")
        price = price + step
        closes.append(price)
    stamps = list(range(len(closes)))
    c = cfg(ma_period=3, short_ma_period=3, long_ma_period=5)
    snaps = build_snapshots(closes, stamps, c)
    strat = Strategy(c)
    entropy = shannon_entropy(close_returns(closes), bins=8)
    assert entropy > D("0.70")
    last = None
    for snap in snaps:
        last = strat.evaluate(snap, None)
    assert last is not None
    assert last.side != "buy"
    assert last.kind == "HOLD"


def test_daily_pnl_score_clamps_and_is_independent() -> None:
    assert daily_pnl_score(D("25000"), D("10000")) == D("1")
    assert daily_pnl_score(D("-25000"), D("10000")) == D("-1")
    assert daily_pnl_score(D("5000"), D("10000")) == D("0.5")
    granville, pnl = paired_indicator_scores(D("0"), D("1"))
    assert granville == D("0")
    assert pnl == D("1")
    granville, pnl = paired_indicator_scores(D("1"), D("-1"))
    assert granville == D("1")
    assert pnl == D("-1")


def test_realtime_daily_pnl_includes_unrealized() -> None:
    pnl = realtime_daily_pnl(D("-100"), D("110"), D("0.001"), D("100"))
    assert pnl == D("-100") + (D("110") - D("100")) * D("0.001")


def test_granville_partial_and_does_not_fire() -> None:
    clauses = {
        "BUY1": {
            "prev_ma_down": True,
            "ma_flat_or_up": True,
            "crossed_up": False,
        },
        "BUY2": {"ma_uptrend": True, "crossed_down": False},
    }
    score = granville_pullback_score(clauses)
    assert score > D("0")
    assert score < D("1")
    assert not all(clauses["BUY1"].values())


def test_granville_and_daily_pnl_both_reported() -> None:
    g = granville_pullback_score(
        {"BUY1": {"a": True, "b": True, "c": True}, "BUY2": {"a": False, "b": False}}
    )
    p = daily_pnl_score(D("-8000"), D("10000"))
    left, right = paired_indicator_scores(g, p)
    assert left == D("1")
    assert right == D("-0.8")
    assert left != D("0") or right != D("0")
