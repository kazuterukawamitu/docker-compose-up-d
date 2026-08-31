from bitbank_bot.market_data import Candle
from bitbank_bot.money import D
from bitbank_bot.plugins import granville_pullback, ma_crossover, sakata_patterns
from bitbank_bot.strategy import Signal

from helpers import snap


def test_hold_requires_reason() -> None:
    waiting = Signal.wait("no setup yet")
    assert waiting.kind == "HOLD"
    assert waiting.reason == "no setup yet"
    assert waiting.score == D("0")


def test_sakata_three_soldiers() -> None:
    def c(o: str, h: str, low: str, cl: str, ts: int) -> Candle:
        return Candle(open=D(o), high=D(h), low=D(low), close=D(cl), volume=D("1"), timestamp_ms=ts)

    candles = [
        c("100", "110", "99", "109", 1),
        c("109", "120", "108", "119", 2),
        c("119", "130", "118", "129", 3),
    ]
    signal = sakata_patterns(candles)
    assert signal.kind == "SAKATA_3_SOLDIERS"
    assert signal.side == "buy"


def test_granville_hold_when_not_uptrend() -> None:
    signal = granville_pullback(snap())
    assert signal.kind == "HOLD"
    assert "granville" in signal.reason


def test_ma_crossover_golden() -> None:
    signal = ma_crossover(snap(golden_cross=True))
    assert signal.kind == "MA_GOLDEN"
    assert signal.side == "buy"
