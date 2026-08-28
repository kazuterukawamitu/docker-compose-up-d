from decimal import Decimal

from bitbank_bot.models import Candle, MaTrend, Side, Snapshot, Ticker
from bitbank_bot.strategy.granville import GranvilleStrategy


def _dec(values: list[float]) -> tuple[Decimal, ...]:
    return tuple(Decimal(str(v)) for v in values)


def _candles(closes: list[float]) -> tuple[Candle, ...]:
    out: list[Candle] = []
    for i, close in enumerate(closes):
        px = Decimal(str(close))
        out.append(
            Candle(
                timestamp_ms=1_700_000_000_000 + i * 60_000,
                open=px,
                high=px,
                low=px,
                close=px,
                volume=Decimal("1"),
            )
        )
    return tuple(out)


def _snapshot(
    *,
    closes: list[float],
    ma: list[float],
    trend: MaTrend,
    prev_trend: MaTrend,
    fast: list[float] | None = None,
    slow: list[float] | None = None,
) -> Snapshot:
    last = Decimal(str(closes[-1]))
    ticker = Ticker(
        pair="btc_jpy",
        last=last,
        bid=last,
        ask=last,
        high=last,
        low=last,
        volume=Decimal("1"),
        timestamp_ms=1,
    )
    zeros = _dec([0] * len(closes))
    return Snapshot(
        candles=_candles(closes),
        ticker=ticker,
        ma=_dec(ma),
        fast_ma=_dec(fast or ma),
        slow_ma=_dec(slow or ma),
        rsi=zeros,
        macd=zeros,
        macd_signal=zeros,
        atr=zeros,
        bb_upper=zeros,
        bb_mid=_dec(ma),
        bb_lower=zeros,
        ma_trend=trend,
        prev_ma_trend=prev_trend,
    )


def test_rule1_buy_flattening_cross_up(settings) -> None:
    strategy = GranvilleStrategy(settings)
    snap = _snapshot(
        closes=[100, 101, 110],
        ma=[105, 104, 104],
        trend=MaTrend.FLAT,
        prev_trend=MaTrend.DOWN,
    )
    signal = strategy.evaluate(snap)
    assert signal.side is Side.BUY
    assert signal.rule_id == 1
    assert signal.take_profit_pct == Decimal("0.03")


def test_rule2_buy_uptrend_cross_down(settings) -> None:
    strategy = GranvilleStrategy(settings)
    snap = _snapshot(
        closes=[110, 108, 100],
        ma=[100, 102, 104],
        trend=MaTrend.UP,
        prev_trend=MaTrend.UP,
        fast=[90, 100, 111],
        slow=[100, 100, 110],
    )
    signal = strategy.evaluate(snap)
    assert signal.side is Side.BUY
    assert signal.rule_id == 2
    assert signal.take_profit_pct == Decimal("0.08")


def test_rule2_without_golden_cross_tp5(settings) -> None:
    strategy = GranvilleStrategy(settings)
    snap = _snapshot(
        closes=[110, 108, 100],
        ma=[100, 102, 104],
        trend=MaTrend.UP,
        prev_trend=MaTrend.UP,
        fast=[90, 90, 90],
        slow=[100, 100, 100],
    )
    signal = strategy.evaluate(snap)
    assert signal.side is Side.BUY
    assert signal.rule_id == 2
    assert signal.take_profit_pct == Decimal("0.05")


def test_rule7_sell_cross_up_still_downtrend(settings) -> None:
    strategy = GranvilleStrategy(settings)
    snap = _snapshot(
        closes=[90, 95, 105],
        ma=[100, 99, 98],
        trend=MaTrend.DOWN,
        prev_trend=MaTrend.DOWN,
    )
    signal = strategy.evaluate(snap)
    assert signal.side is Side.SELL
    assert signal.rule_id == 7


def test_rule6_sell_breakdown_not_uptrend(settings) -> None:
    strategy = GranvilleStrategy(settings)
    snap = _snapshot(
        closes=[110, 105, 95],
        ma=[100, 100, 100],
        trend=MaTrend.FLAT,
        prev_trend=MaTrend.FLAT,
    )
    signal = strategy.evaluate(snap)
    assert signal.side is Side.SELL
    assert signal.rule_id == 6


def test_rule3_buy_after_extension_pullback(settings) -> None:
    strategy = GranvilleStrategy(settings)
    stretch = _snapshot(
        closes=[100, 104, 106],
        ma=[100, 100, 100],
        trend=MaTrend.UP,
        prev_trend=MaTrend.UP,
    )
    strategy.evaluate(stretch)
    assert strategy.memory.extended_up_5
    pullback = _snapshot(
        closes=[104, 106, 105.2],
        ma=[100, 100, 100],
        trend=MaTrend.UP,
        prev_trend=MaTrend.UP,
    )
    strategy.evaluate(pullback)
    assert strategy.memory.pullback_no_touch
    bounce = _snapshot(
        closes=[106, 105.2, 106.1],
        ma=[100, 100, 100],
        trend=MaTrend.UP,
        prev_trend=MaTrend.UP,
    )
    signal = strategy.evaluate(bounce)
    assert signal.side is Side.BUY
    assert signal.rule_id == 3
    assert signal.take_profit_pct == Decimal("0.04")


def test_rule4_buy_from_5pct_below_downtrend(settings) -> None:
    strategy = GranvilleStrategy(settings)
    first = _snapshot(
        closes=[100, 96, 94],
        ma=[100, 100, 100],
        trend=MaTrend.DOWN,
        prev_trend=MaTrend.DOWN,
    )
    strategy.evaluate(first)
    assert strategy.memory.extended_down_5
    second = _snapshot(
        closes=[96, 94, 95],
        ma=[100, 100, 100],
        trend=MaTrend.DOWN,
        prev_trend=MaTrend.DOWN,
    )
    signal = strategy.evaluate(second)
    assert signal.side is Side.BUY
    assert signal.rule_id == 4


def test_rule5_sell_after_4pct_extension_declines(settings) -> None:
    strategy = GranvilleStrategy(settings)
    stretch = _snapshot(
        closes=[100, 103, 105],
        ma=[100, 100, 100],
        trend=MaTrend.UP,
        prev_trend=MaTrend.UP,
    )
    strategy.evaluate(stretch)
    assert strategy.memory.extended_up_4
    fade = _snapshot(
        closes=[103, 105, 103.5],
        ma=[100, 100, 100],
        trend=MaTrend.UP,
        prev_trend=MaTrend.UP,
    )
    signal = strategy.evaluate(fade)
    assert signal.side is Side.SELL
    assert signal.rule_id == 5


def test_rule8_failed_bounce_sell(settings) -> None:
    strategy = GranvilleStrategy(settings)
    dump = _snapshot(
        closes=[100, 97, 95.5],
        ma=[100, 100, 100],
        trend=MaTrend.DOWN,
        prev_trend=MaTrend.DOWN,
    )
    strategy.evaluate(dump)
    assert strategy.memory.extended_down_4
    bounce = _snapshot(
        closes=[97, 95.5, 96.4],
        ma=[100, 100, 100],
        trend=MaTrend.DOWN,
        prev_trend=MaTrend.DOWN,
    )
    strategy.evaluate(bounce)
    assert strategy.memory.bounce_no_touch
    fail = _snapshot(
        closes=[95.5, 96.4, 95.8],
        ma=[100, 100, 100],
        trend=MaTrend.DOWN,
        prev_trend=MaTrend.DOWN,
    )
    signal = strategy.evaluate(fail)
    assert signal.side is Side.SELL
    assert signal.rule_id == 8
