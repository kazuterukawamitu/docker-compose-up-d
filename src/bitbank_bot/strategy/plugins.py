"""Optional named strategies. Disabled unless listed in STRATEGIES."""

from __future__ import annotations

from decimal import Decimal

from bitbank_bot.config import Settings
from bitbank_bot.models import Signal, Side, Snapshot
from bitbank_bot.strategy.base import CombinedStrategy, StrategyBase
from bitbank_bot.strategy.granville import GranvilleStrategy


class GoldenCrossStrategy(StrategyBase):
    name = "golden_cross"

    def evaluate(self, snapshot: Snapshot) -> Signal:
        if len(snapshot.fast_ma) < 2 or len(snapshot.slow_ma) < 2:
            return Signal.hold()
        prev_fast, fast = snapshot.fast_ma[-2], snapshot.fast_ma[-1]
        prev_slow, slow = snapshot.slow_ma[-2], snapshot.slow_ma[-1]
        if prev_fast <= prev_slow and fast > slow and fast > 0 and slow > 0:
            return Signal(Side.BUY, "golden cross", take_profit_pct=Decimal("0.05"))
        return Signal.hold()


class DeathCrossStrategy(StrategyBase):
    name = "death_cross"

    def evaluate(self, snapshot: Snapshot) -> Signal:
        if len(snapshot.fast_ma) < 2 or len(snapshot.slow_ma) < 2:
            return Signal.hold()
        prev_fast, fast = snapshot.fast_ma[-2], snapshot.fast_ma[-1]
        prev_slow, slow = snapshot.slow_ma[-2], snapshot.slow_ma[-1]
        if prev_fast >= prev_slow and fast < slow and fast > 0 and slow > 0:
            return Signal(Side.SELL, "death cross", size_mode="all")
        return Signal.hold()


class RsiContrarianStrategy(StrategyBase):
    name = "rsi"

    def evaluate(self, snapshot: Snapshot) -> Signal:
        if not snapshot.rsi:
            return Signal.hold()
        value = snapshot.rsi[-1]
        if value <= 0:
            return Signal.hold()
        if value < Decimal("30"):
            return Signal(Side.BUY, f"RSI oversold {value}", take_profit_pct=Decimal("0.03"))
        if value > Decimal("70"):
            return Signal(Side.SELL, f"RSI overbought {value}", size_mode="all")
        return Signal.hold()


class MacdStrategy(StrategyBase):
    name = "macd"

    def evaluate(self, snapshot: Snapshot) -> Signal:
        if len(snapshot.macd) < 2 or len(snapshot.macd_signal) < 2:
            return Signal.hold()
        prev_m, macd = snapshot.macd[-2], snapshot.macd[-1]
        prev_s, signal = snapshot.macd_signal[-2], snapshot.macd_signal[-1]
        if prev_m <= prev_s and macd > signal:
            return Signal(Side.BUY, "MACD cross up", take_profit_pct=Decimal("0.04"))
        if prev_m >= prev_s and macd < signal:
            return Signal(Side.SELL, "MACD cross down", size_mode="all")
        return Signal.hold()


class AtrBreakoutStrategy(StrategyBase):
    name = "atr_breakout"

    def evaluate(self, snapshot: Snapshot) -> Signal:
        if len(snapshot.candles) < 2 or not snapshot.atr:
            return Signal.hold()
        atr = snapshot.atr[-1]
        if atr <= 0:
            return Signal.hold()
        candle = snapshot.candles[-1]
        prev = snapshot.candles[-2]
        if candle.close > prev.high + atr:
            return Signal(Side.BUY, "ATR upside breakout", take_profit_pct=Decimal("0.04"))
        if candle.close < prev.low - atr:
            return Signal(Side.SELL, "ATR downside breakout", size_mode="all")
        return Signal.hold()


_REGISTRY: dict[str, type[StrategyBase]] = {
    "granville": GranvilleStrategy,
    "golden_cross": GoldenCrossStrategy,
    "death_cross": DeathCrossStrategy,
    "rsi": RsiContrarianStrategy,
    "macd": MacdStrategy,
    "atr_breakout": AtrBreakoutStrategy,
}


def build_strategies(settings: Settings) -> CombinedStrategy:
    built: list[StrategyBase] = []
    for name in settings.strategies:
        cls = _REGISTRY.get(name)
        if cls is None:
            continue
        if cls is GranvilleStrategy:
            built.append(GranvilleStrategy(settings))
        else:
            built.append(cls())
    if not built:
        built.append(GranvilleStrategy(settings))
    return CombinedStrategy(built)
