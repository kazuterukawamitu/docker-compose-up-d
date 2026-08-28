from decimal import Decimal

from bitbank_bot.market.indicators import atr, bollinger, classify_ma_trend, ema, rsi, sma
from bitbank_bot.models import MaTrend


def test_sma_period_3() -> None:
    values = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")]
    result = sma(values, 3)
    assert result[0] == Decimal("0")
    assert result[1] == Decimal("0")
    assert result[2] == Decimal("2")
    assert result[3] == Decimal("3")
    assert result[4] == Decimal("4")


def test_ema_warms_up() -> None:
    values = [Decimal(str(v)) for v in range(1, 11)]
    result = ema(values, 3)
    assert result[1] == Decimal("0")
    assert result[2] > 0
    assert result[-1] > result[2]


def test_rsi_uptrend_is_high() -> None:
    values = [Decimal(str(i)) for i in range(1, 30)]
    result = rsi(values, 14)
    assert result[-1] > Decimal("70")


def test_atr_positive() -> None:
    highs = [Decimal("10"), Decimal("12"), Decimal("11"), Decimal("13"), Decimal("14")]
    lows = [Decimal("9"), Decimal("10"), Decimal("10"), Decimal("11"), Decimal("12")]
    closes = [Decimal("9.5"), Decimal("11"), Decimal("10.5"), Decimal("12.5"), Decimal("13")]
    result = atr(highs, lows, closes, 3)
    assert result[-1] > 0


def test_bollinger_bands_wrap_mid() -> None:
    values = [Decimal(str(x)) for x in [10, 11, 12, 11, 10, 11, 12, 13, 12, 11] * 3]
    upper, mid, lower = bollinger(values, 20, Decimal("2"))
    assert upper[-1] >= mid[-1] >= lower[-1]


def test_classify_ma_trend() -> None:
    up = [Decimal("100") + Decimal(i) for i in range(10)]
    down = [Decimal("100") - Decimal(i) for i in range(10)]
    flat = [Decimal("100")] * 10
    assert classify_ma_trend(up, 3, Decimal("0.001")) is MaTrend.UP
    assert classify_ma_trend(down, 3, Decimal("0.001")) is MaTrend.DOWN
    assert classify_ma_trend(flat, 3, Decimal("0.001")) is MaTrend.FLAT
