"""README MA / Granville-style rules for BTC/JPY.

Buy rules:
1. Downtrending MA flattens or turns up, price crosses above MA → buy, TP +3%
2. MA uptrend, price crosses below MA → buy, TP +8% on golden cross else +5%
3. Price was ≥5% above MA, pulled back without touching MA, then rose → buy, TP +4%
4. Price was ≥5% below a downtrending MA, then rose → buy, TP +5%

Sell rules:
5. Price was ≥4% above MA, then declined → sell all
6. Price declines and crosses below MA (unless rule 2 applies) → sell all
7. Price crosses up through a still-downtrending MA → sell all
8. Price was ≥4% below MA, rose without reaching MA, then fell → sell all
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from bitbank_bot.config import Settings
from bitbank_bot.market.indicators import crossed_above, crossed_below
from bitbank_bot.models import MaTrend, Signal, Side, Snapshot
from bitbank_bot.strategy.base import StrategyBase

PCT_3 = Decimal("0.03")
PCT_4 = Decimal("0.04")
PCT_5 = Decimal("0.05")
PCT_8 = Decimal("0.08")


@dataclass(slots=True)
class PatternMemory:
    extended_up_5: bool = False
    pullback_no_touch: bool = False
    extended_up_4: bool = False
    extended_down_5: bool = False
    extended_down_4: bool = False
    bounce_no_touch: bool = False


class GranvilleStrategy(StrategyBase):
    name = "granville"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.memory = PatternMemory()

    def evaluate(self, snapshot: Snapshot) -> Signal:
        if len(snapshot.candles) < 3 or len(snapshot.ma) < 3:
            return Signal.hold("not enough candles")
        price = snapshot.candles[-1].close
        prev_price = snapshot.candles[-2].close
        ma = snapshot.ma[-1]
        prev_ma = snapshot.ma[-2]
        if ma <= 0 or prev_ma <= 0:
            return Signal.hold("MA not ready")

        dist = (price - ma) / ma
        declining = price < prev_price
        rising = price > prev_price
        cross_up = crossed_above(prev_price, prev_ma, price, ma)
        cross_down = crossed_below(prev_price, prev_ma, price, ma)
        golden = _golden_cross(snapshot)

        self._update_memory(price, ma, dist, declining, rising)

        sell = self._sell_signal(
            snapshot=snapshot,
            dist=dist,
            declining=declining,
            cross_up=cross_up,
            cross_down=cross_down,
        )
        if sell is not None:
            self._consume(sell.rule_id)
            return sell

        buy = self._buy_signal(
            snapshot=snapshot,
            dist=dist,
            rising=rising,
            cross_up=cross_up,
            cross_down=cross_down,
            golden=golden,
        )
        if buy is not None:
            self._consume(buy.rule_id)
            return buy
        return Signal.hold()

    def _buy_signal(
        self,
        *,
        snapshot: Snapshot,
        dist: Decimal,
        rising: bool,
        cross_up: bool,
        cross_down: bool,
        golden: bool,
    ) -> Signal | None:
        trend = snapshot.ma_trend
        prev_trend = snapshot.prev_ma_trend

        # Rule 1: downtrend MA flattened/turned up + cross above.
        if cross_up and prev_trend is MaTrend.DOWN and trend in {MaTrend.FLAT, MaTrend.UP}:
            return Signal(Side.BUY, "rule1 MA flattened/up + cross above", 1, PCT_3)

        # Rule 2: uptrend MA + cross below (dip buy). Overrides rule 6.
        if cross_down and trend is MaTrend.UP:
            tp = PCT_8 if golden else PCT_5
            reason = "rule2 uptrend pullback" + (" golden cross TP8%" if golden else " TP5%")
            return Signal(Side.BUY, reason, 2, tp)

        # Rule 3: extended ≥5% above, pullback without MA touch, then rise.
        if self.memory.pullback_no_touch and rising and dist > 0:
            return Signal(Side.BUY, "rule3 bounce after 5% extension", 3, PCT_4)

        # Rule 4: ≥5% below downtrending MA, then rise.
        if self.memory.extended_down_5 and rising and trend is MaTrend.DOWN:
            return Signal(Side.BUY, "rule4 bounce from 5% below downtrend MA", 4, PCT_5)
        return None

    def _sell_signal(
        self,
        *,
        snapshot: Snapshot,
        dist: Decimal,
        declining: bool,
        cross_up: bool,
        cross_down: bool,
    ) -> Signal | None:
        trend = snapshot.ma_trend

        # Rule 5: was ≥4% above MA, then declined.
        if self.memory.extended_up_4 and declining:
            return Signal(Side.SELL, "rule5 fade after 4% above MA", 5, size_mode="all")

        # Rule 6: declining cross below MA, except uptrend dip-buy (rule 2).
        if cross_down and declining and trend is not MaTrend.UP:
            return Signal(Side.SELL, "rule6 breakdown through MA", 6, size_mode="all")

        # Rule 7: cross up through a still-downtrending MA.
        if cross_up and trend is MaTrend.DOWN:
            return Signal(Side.SELL, "rule7 rally into downtrending MA", 7, size_mode="all")

        # Rule 8: ≥4% below, bounce without reaching MA, then fall.
        if self.memory.bounce_no_touch and declining and dist < 0:
            return Signal(Side.SELL, "rule8 failed bounce below MA", 8, size_mode="all")
        return None

    def _update_memory(
        self,
        price: Decimal,
        ma: Decimal,
        dist: Decimal,
        declining: bool,
        rising: bool,
    ) -> None:
        if dist >= PCT_5:
            self.memory.extended_up_5 = True
        if dist >= PCT_4:
            self.memory.extended_up_4 = True
        if dist <= -PCT_5:
            self.memory.extended_down_5 = True
        if dist <= -PCT_4:
            self.memory.extended_down_4 = True

        if self.memory.extended_up_5 and declining and price > ma:
            self.memory.pullback_no_touch = True
        if self.memory.extended_up_5 and price <= ma:
            self.memory.extended_up_5 = False
            self.memory.pullback_no_touch = False

        if self.memory.extended_down_4 and rising and price < ma:
            self.memory.bounce_no_touch = True
        if self.memory.extended_down_4 and price >= ma:
            self.memory.extended_down_4 = False
            self.memory.bounce_no_touch = False

        if price <= ma:
            self.memory.extended_up_4 = False
        if price >= ma:
            self.memory.extended_down_5 = False

    def _consume(self, rule_id: int | None) -> None:
        if rule_id == 3:
            self.memory.extended_up_5 = False
            self.memory.pullback_no_touch = False
        elif rule_id == 4:
            self.memory.extended_down_5 = False
        elif rule_id == 5:
            self.memory.extended_up_4 = False
        elif rule_id == 8:
            self.memory.extended_down_4 = False
            self.memory.bounce_no_touch = False


def _golden_cross(snapshot: Snapshot) -> bool:
    if len(snapshot.fast_ma) < 2 or len(snapshot.slow_ma) < 2:
        return False
    fast, prev_fast = snapshot.fast_ma[-1], snapshot.fast_ma[-2]
    slow, prev_slow = snapshot.slow_ma[-1], snapshot.slow_ma[-2]
    if fast <= 0 or slow <= 0 or prev_fast <= 0 or prev_slow <= 0:
        return False
    return prev_fast <= prev_slow and fast > slow
