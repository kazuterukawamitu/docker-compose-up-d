from __future__ import annotations

from decimal import Decimal
from typing import Any

from bitbank_bot.market_data import Candle
from bitbank_bot.multi_timeframe import evaluate_htf
from tests.helpers import cfg


def _bars(n: int, start: int, step: int) -> list[Candle]:
    hour = 3_600_000
    out: list[Candle] = []
    for i in range(n):
        price = Decimal(start + i * step)
        out.append(
            Candle(
                price,
                price,
                price,
                price,
                Decimal("1"),
                1_600_000_000_000 + i * hour,
            )
        )
    return out


def _rows(candles: list[Candle]) -> list[list[Any]]:
    return [
        [str(c.open), str(c.high), str(c.low), str(c.close), str(c.volume), c.timestamp_ms]
        for c in candles
    ]


class HtfRest:
    def __init__(self, four: list[Candle], day: list[Candle]) -> None:
        self.four = four
        self.day = day

    def get_candlestick(self, pair: str, candle_type: str, date_key: str) -> list[list[Any]]:
        assert pair == "btc_jpy"
        if candle_type == "4hour":
            return _rows(self.four)
        if candle_type == "1day":
            return _rows(self.day)
        return []


def test_both_down_blocks_buy() -> None:
    c = cfg(ma_period=5, ma_slope_threshold=Decimal("0.0005"))
    four = _bars(12, 10_000_000, -50_000)
    day = _bars(12, 9_000_000, -40_000)
    verdict = evaluate_htf(HtfRest(four, day), c)  # type: ignore[arg-type]
    assert verdict.allow_buy is False
    assert verdict.reason == "htf_downtrend"
    assert verdict.trend_4h == "DOWN"
    assert verdict.trend_1d == "DOWN"


def test_mixed_trends_allow_buy() -> None:
    c = cfg(ma_period=5, ma_slope_threshold=Decimal("0.0005"))
    four = _bars(12, 10_000_000, 50_000)
    day = _bars(12, 9_000_000, -40_000)
    verdict = evaluate_htf(HtfRest(four, day), c)  # type: ignore[arg-type]
    assert verdict.allow_buy is True
    assert verdict.reason == "htf_ok"


def test_missing_htf_blocks_buy() -> None:
    c = cfg(ma_period=5)
    verdict = evaluate_htf(HtfRest([], []), c)  # type: ignore[arg-type]
    assert verdict.allow_buy is False
    assert verdict.reason == "htf_unavailable"


def test_htf_parse_failure_is_logged(caplog) -> None:
    class BadRowRest:
        def get_candlestick(self, pair: str, candle_type: str, date_key: str) -> list:
            return [["bad"], [1, 2, 3]]

    with caplog.at_level("INFO", logger="bitbank_bot"):
        verdict = evaluate_htf(BadRowRest(), cfg(ma_period=5))  # type: ignore[arg-type]
    assert verdict.allow_buy is False
    assert verdict.reason == "htf_unavailable"
    assert "htf parse_ohlcv failed" in caplog.text
