from decimal import Decimal

from bitbank_bot.decimal_utils import d
from bitbank_bot.market.indicators import (
    atr,
    bollinger,
    crossed_above,
    crossed_below,
    ema,
    macd,
    rsi,
    sma,
)
from bitbank_bot.models import Candle


def test_sma_known_window() -> None:
    values = [d(x) for x in (1, 2, 3, 4, 5)]
    out = sma(values, 3)
    assert out[1] is None
    assert out[2] == Decimal("2")
    assert out[4] == Decimal("4")


def test_ema_seeds_from_sma() -> None:
    values = [d(x) for x in (10, 10, 10, 12)]
    out = ema(values, 3)
    assert out[1] is None
    assert out[2] == Decimal("10")
    assert out[3] is not None
    assert out[3] > Decimal("10")


def test_rsi_atr_macd_bollinger_produce_values() -> None:
    closes = [d(100 + i) for i in range(40)]
    candles = [
        Candle(ts=i, open=c, high=c + 1, low=c - 1, close=c, volume=Decimal("1"))
        for i, c in enumerate(closes)
    ]
    rsi_line = rsi(closes, 14)
    assert rsi_line[-1] is not None
    assert Decimal("50") < rsi_line[-1] <= Decimal("100")
    atr_line = atr(candles, 14)
    assert atr_line[-1] is not None
    macd_line, signal, hist = macd(closes)
    assert macd_line[-1] is not None
    assert signal[-1] is not None
    assert hist[-1] is not None
    upper, mid, lower = bollinger(closes, 20)
    assert mid[-1] is not None
    assert upper[-1] > mid[-1] > lower[-1]  # type: ignore[operator]


def test_cross_helpers() -> None:
    assert crossed_above(Decimal("99"), Decimal("100"), Decimal("101"), Decimal("100"))
    assert not crossed_above(Decimal("101"), Decimal("100"), Decimal("102"), Decimal("100"))
    assert crossed_below(Decimal("101"), Decimal("100"), Decimal("99"), Decimal("100"))
