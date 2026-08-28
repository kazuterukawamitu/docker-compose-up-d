from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from bitbank_bot.config import Settings
from bitbank_bot.market.indicators import (
    crossed_above,
    crossed_below,
    deviation,
    ema,
    ma_series,
    slope_of,
)
from bitbank_bot.models import Action, Candle, Position, Signal, Slope


HOLD = Signal(action="HOLD", rule_id="none", reason="no setup")


@dataclass
class StrategyMemory:
    prev_slope: Slope | None = None
    ma_was_down: bool = False
    extended_plus_5: bool = False
    declined_from_plus_5: bool = False
    extended_minus_5_down_ma: bool = False
    extended_minus_4: bool = False
    rose_from_minus_4: bool = False
    last_close: Decimal | None = None
    last_ma: Decimal | None = None
    last_fast: Decimal | None = None
    last_slow: Decimal | None = None
    golden_cross_regime: bool = False
    processed_ts: int = 0


@dataclass
class PreparedBar:
    ts: int
    close: Decimal
    ma: Decimal
    ema_fast: Decimal
    ema_slow: Decimal
    slope: Slope
    golden_cross_event: bool
    death_cross_event: bool


class MaRuleStrategy:
    """README moving-average rules. Does not call the exchange."""

    def __init__(self, settings: Settings, memory: StrategyMemory | None = None) -> None:
        self.settings = settings
        self.memory = memory or StrategyMemory()

    def prepare(self, candles: list[Candle]) -> list[PreparedBar]:
        closes = [c.close for c in candles]
        ma = ma_series(closes, self.settings.ma_period, self.settings.ma_kind)
        fast = ema(closes, self.settings.ema_fast)
        slow = ema(closes, self.settings.ema_slow)
        out: list[PreparedBar] = []
        lookback = self.settings.slope_lookback
        for i, candle in enumerate(candles):
            if ma[i] is None or fast[i] is None or slow[i] is None:
                continue
            prev_idx = i - lookback
            if prev_idx < 0 or ma[prev_idx] is None:
                continue
            slope = slope_of(ma[i], ma[prev_idx], self.settings.flat_threshold)  # type: ignore[arg-type]
            golden = False
            death = False
            if i > 0 and fast[i - 1] is not None and slow[i - 1] is not None:
                golden = fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]  # type: ignore[operator]
                death = fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]  # type: ignore[operator]
            out.append(
                PreparedBar(
                    ts=candle.ts,
                    close=candle.close,
                    ma=ma[i],  # type: ignore[arg-type]
                    ema_fast=fast[i],  # type: ignore[arg-type]
                    ema_slow=slow[i],  # type: ignore[arg-type]
                    slope=slope,
                    golden_cross_event=golden,
                    death_cross_event=death,
                )
            )
        return out

    def evaluate(
        self,
        candles: list[Candle],
        position: Position,
        live_price: Decimal | None = None,
    ) -> Signal:
        bars = self.prepare(candles)
        if len(bars) < 2:
            return HOLD
        for bar in bars[:-1]:
            if bar.ts <= self.memory.processed_ts:
                continue
            self._observe(bar)
            self.memory.processed_ts = bar.ts
        latest = bars[-1]
        if latest.ts > self.memory.processed_ts:
            signal = self._signal_for(latest, position)
            self._observe(latest)
            self.memory.processed_ts = latest.ts
            if position.is_open:
                position.bars_held += 1
            return signal
        if position.is_open and live_price is not None and position.take_profit_pct > 0:
            target = position.entry_price * (Decimal("1") + position.take_profit_pct)
            if live_price >= target:
                return Signal(
                    action="SELL",
                    rule_id="take_profit",
                    reason=f"take-profit {position.take_profit_pct * 100}% from rule {position.rule_id}",
                    target_kind="flatten",
                )
        return HOLD

    def _observe(self, bar: PreparedBar) -> None:
        mem = self.memory
        if mem.last_close is not None:
            if bar.slope == "down":
                mem.ma_was_down = True
            if bar.slope in {"flat", "up"} and mem.prev_slope == "down":
                mem.ma_was_down = True
            dev = deviation(bar.close, bar.ma)
            if dev >= Decimal("0.05"):
                mem.extended_plus_5 = True
            if mem.extended_plus_5 and bar.close < mem.last_close and bar.close > bar.ma:
                mem.declined_from_plus_5 = True
            if bar.close <= bar.ma:
                mem.extended_plus_5 = False
                mem.declined_from_plus_5 = False
            if bar.slope == "down" and dev <= Decimal("-0.05"):
                mem.extended_minus_5_down_ma = True
            if bar.close >= bar.ma:
                mem.extended_minus_5_down_ma = False
            if dev <= Decimal("-0.04"):
                mem.extended_minus_4 = True
            if mem.extended_minus_4 and bar.close > mem.last_close and bar.close < bar.ma:
                mem.rose_from_minus_4 = True
            if bar.close >= bar.ma:
                mem.extended_minus_4 = False
                mem.rose_from_minus_4 = False
        mem.golden_cross_regime = bar.ema_fast > bar.ema_slow
        mem.prev_slope = bar.slope
        mem.last_close = bar.close
        mem.last_ma = bar.ma
        mem.last_fast = bar.ema_fast
        mem.last_slow = bar.ema_slow

    def _signal_for(self, bar: PreparedBar, position: Position) -> Signal:
        mem = self.memory
        if mem.last_close is None or mem.last_ma is None:
            return HOLD

        prev_close = mem.last_close
        prev_ma = mem.last_ma
        up_cross = crossed_above(prev_close, prev_ma, bar.close, bar.ma)
        down_cross = crossed_below(prev_close, prev_ma, bar.close, bar.ma)
        declining = bar.close < prev_close
        rising = bar.close > prev_close
        dev = deviation(bar.close, bar.ma)
        plus4_now_or_was = dev >= Decimal("0.04") or mem.extended_plus_5

        if position.is_open and position.bars_held >= self.settings.min_hold_bars:
            tp = position.take_profit_pct
            if tp > 0 and bar.close >= position.entry_price * (Decimal("1") + tp):
                return Signal(
                    action="SELL",
                    rule_id="take_profit",
                    reason=f"take-profit {tp * 100}% from rule {position.rule_id}",
                    target_kind="flatten",
                )
            # Rule 5
            if plus4_now_or_was and declining and bar.close > bar.ma:
                return Signal(
                    action="SELL",
                    rule_id="sell_5",
                    reason="価格がMAより4%以上上に離れた後に下降",
                    target_kind="flatten",
                )
            # Rule 6
            if down_cross and declining:
                return Signal(
                    action="SELL",
                    rule_id="sell_6",
                    reason="下降してMAを下抜け、さらに下降",
                    target_kind="flatten",
                )
            # Rule 7
            if up_cross and bar.slope == "down":
                return Signal(
                    action="SELL",
                    rule_id="sell_7",
                    reason="下降トレンドのMAをクロスして上昇",
                    target_kind="flatten",
                )
            # Rule 8
            if mem.rose_from_minus_4 and declining and bar.close < bar.ma:
                return Signal(
                    action="SELL",
                    rule_id="sell_8",
                    reason="MAより4%以上下に下降後、MA未到達で再上昇し再び下落",
                    target_kind="flatten",
                )
            if self.settings.wiki_cross_rules:
                short_falling = mem.last_fast is None or bar.ema_fast <= mem.last_fast
                if bar.death_cross_event and short_falling:
                    return Signal(
                        action="SELL",
                        rule_id="wiki_death_cross",
                        reason="短期MAが下向きに長期MAを下抜け",
                        target_kind="flatten",
                    )

        if position.is_open:
            return HOLD

        # Rule 1: MA was down, now flat/up, price crosses above MA
        ma_turned = mem.ma_was_down and bar.slope in {"flat", "up"}
        if ma_turned and up_cross:
            return Signal(
                action="BUY",
                rule_id="buy_1",
                reason="下降トレンドだったMAが横ばい/上昇となり価格が上抜け",
                take_profit_pct=Decimal("0.03"),
                target_kind=self.settings.order_size_mode,
            )
        # Rule 2: MA uptrend, price crosses below MA
        if bar.slope == "up" and down_cross:
            tp = Decimal("0.08") if mem.golden_cross_regime or bar.ema_fast > bar.ema_slow else Decimal("0.05")
            return Signal(
                action="BUY",
                rule_id="buy_2",
                reason="上昇トレンドのMAを価格が下抜け" + ("（ゴールデンクロス）" if tp == Decimal("0.08") else ""),
                take_profit_pct=tp,
                target_kind=self.settings.order_size_mode,
            )
        # Rule 3: +5% extension, pullback without touching MA, then rise
        if mem.extended_plus_5 and mem.declined_from_plus_5 and rising and bar.close > bar.ma:
            return Signal(
                action="BUY",
                rule_id="buy_3",
                reason="MAより5%以上上に離れた後、MA未到達で下降し再上昇",
                take_profit_pct=Decimal("0.04"),
                target_kind=self.settings.order_size_mode,
            )
        # Rule 4: -5% below declining MA, then rise
        if mem.extended_minus_5_down_ma and rising and bar.slope == "down" and bar.close < bar.ma:
            return Signal(
                action="BUY",
                rule_id="buy_4",
                reason="下降MAより5%以上下に下降した後に再上昇",
                take_profit_pct=Decimal("0.05"),
                target_kind=self.settings.order_size_mode,
            )
        if self.settings.wiki_cross_rules:
            short_rising = mem.last_fast is None or bar.ema_fast >= mem.last_fast
            if bar.golden_cross_event and short_rising:
                return Signal(
                    action="BUY",
                    rule_id="wiki_golden_cross",
                    reason="短期MAが上向きに長期MAを下から上抜け",
                    take_profit_pct=Decimal("0.03"),
                    target_kind=self.settings.order_size_mode,
                )
        return HOLD


def describe_action(action: Action) -> str:
    return {"BUY": "buy BTC", "SELL": "sell BTC", "HOLD": "hold"}[action]
