from decimal import Decimal

from bitbank_bot.config import Config
from bitbank_bot.money import D
from bitbank_bot.strategy import MarketSnapshot, Position
from bitbank_bot.indicators import Trend


def cfg(**kwargs) -> Config:
    return Config(**kwargs)


def snap(**kwargs) -> MarketSnapshot:
    base = dict(
        index=10,
        timestamp_ms=1_700_000_000_000,
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
    base.update(kwargs)
    return MarketSnapshot(**base)


def position(**kwargs) -> Position:
    base = dict(
        amount=D("0.1"),
        average_price=D("100"),
        tp_pct=D("0.03"),
        entry_candle_index=1,
        entry_candle_ts=1,
        actual_execution_jpy=D("10"),
        kind="BUY1",
    )
    base.update(kwargs)
    return Position(**base)
