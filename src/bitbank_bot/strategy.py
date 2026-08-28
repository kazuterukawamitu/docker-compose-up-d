"""README moving-average buy/sell rules. Canonical text is docs/strategy.md."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from bitbank_bot.config import Config
from bitbank_bot.indicators import (
    Trend,
    crossed_down,
    crossed_up,
    interpolate_crossover,
    is_golden_cross,
    ma_trend,
    moving_average,
)
from bitbank_bot.money import D, ONE, pct_offset


@dataclass
class MarketSnapshot:
    index: int
    timestamp_ms: int
    close: Decimal
    prev_close: Decimal
    ma: Decimal
    prev_ma: Decimal
    short_ma: Decimal
    prev_short_ma: Decimal
    long_ma: Decimal
    prev_long_ma: Decimal
    ma_trend: Trend
    prev_ma_trend: Trend
    crossed_up: bool
    crossed_down: bool
    golden_cross: bool
    cross_price: Decimal | None


@dataclass
class Position:
    amount: Decimal
    average_price: Decimal
    tp_pct: Decimal
    entry_candle_index: int
    entry_candle_ts: int
    actual_execution_jpy: Decimal
    kind: str


@dataclass
class Signal:
    kind: str
    side: str | None
    tp_pct: Decimal | None
    reason: str
    golden_cross: bool = False
    cross_price: Decimal | None = None
    peak_price: Decimal | None = None

    @staticmethod
    def hold(reason: str = "no setup") -> "Signal":
        return Signal(kind="HOLD", side=None, tp_pct=None, reason=reason)


class Buy3Machine:
    def __init__(self, extend_pct: Decimal) -> None:
        self.extend_pct = extend_pct
        self.phase = "idle"
        self.peak: Decimal | None = None
        self.prev_close: Decimal | None = None

    def reset(self) -> None:
        self.phase = "idle"
        self.peak = None

    def update(self, close: Decimal, ma: Decimal) -> bool:
        fired = False
        if close <= ma:
            self.reset()
            self.prev_close = close
            return False
        threshold = ma * (ONE + self.extend_pct)
        if self.phase == "idle":
            if close >= threshold:
                self.phase = "extended"
                self.peak = close
        elif self.phase == "extended":
            if self.peak is None or close > self.peak:
                self.peak = close
            elif self.prev_close is not None and close < self.prev_close:
                self.phase = "pullback"
        elif self.phase == "pullback":
            if self.prev_close is not None and close > self.prev_close:
                fired = True
                self.reset()
        self.prev_close = close
        return fired


class Buy4Machine:
    def __init__(self, dip_pct: Decimal) -> None:
        self.dip_pct = dip_pct
        self.phase = "idle"
        self.prev_close: Decimal | None = None

    def update(self, close: Decimal, ma: Decimal, trend: Trend) -> bool:
        fired = False
        if trend != Trend.DOWN:
            self.phase = "idle"
            self.prev_close = close
            return False
        floor = ma * (ONE - self.dip_pct)
        if self.phase == "idle":
            if close <= floor:
                self.phase = "dipped"
        elif self.phase == "dipped":
            if self.prev_close is not None and close > self.prev_close:
                fired = True
                self.phase = "idle"
        self.prev_close = close
        return fired


class Sell1Machine:
    def __init__(self, extend_pct: Decimal) -> None:
        self.extend_pct = extend_pct
        self.phase = "idle"
        self.prev_close: Decimal | None = None

    def update(self, close: Decimal, ma: Decimal) -> bool:
        fired = False
        ceiling = ma * (ONE + self.extend_pct)
        if self.phase == "idle":
            if close >= ceiling:
                self.phase = "extended"
        elif self.phase == "extended":
            if self.prev_close is not None and close < self.prev_close:
                fired = True
                self.phase = "idle"
            elif close < ma:
                self.phase = "idle"
        self.prev_close = close
        return fired


class Sell2Machine:
    def __init__(self) -> None:
        self.phase = "idle"

    def update(self, close: Decimal, prev_close: Decimal, crossed_dn: bool) -> bool:
        fired = False
        falling_now = close < prev_close
        if self.phase == "idle":
            if falling_now:
                self.phase = "crossed" if crossed_dn else "falling"
        elif self.phase == "falling":
            if crossed_dn and falling_now:
                self.phase = "crossed"
            elif not falling_now:
                self.phase = "idle"
        elif self.phase == "crossed":
            if falling_now:
                fired = True
            self.phase = "idle"
        return fired


class Sell4Machine:
    def __init__(self, dip_pct: Decimal) -> None:
        self.dip_pct = dip_pct
        self.phase = "idle"
        self.peak: Decimal | None = None
        self.last_peak: Decimal | None = None
        self.prev_close: Decimal | None = None

    def update(self, close: Decimal, ma: Decimal) -> bool:
        fired = False
        floor = ma * (ONE - self.dip_pct)
        if close >= ma:
            self.phase = "idle"
            self.peak = None
            self.prev_close = close
            return False
        if self.phase == "idle":
            if close <= floor:
                self.phase = "dipped"
        elif self.phase == "dipped":
            if self.prev_close is not None and close > self.prev_close:
                self.phase = "recovery"
                self.peak = close
        elif self.phase == "recovery":
            if self.peak is None or close > self.peak:
                self.peak = close
            elif self.prev_close is not None and close < self.prev_close:
                fired = True
                self.last_peak = self.peak
                self.phase = "idle"
                self.peak = None
        self.prev_close = close
        return fired


class Strategy:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.buy3 = Buy3Machine(cfg.buy3_extend)
        self.buy4 = Buy4Machine(cfg.buy4_dip)
        self.sell1 = Sell1Machine(cfg.sell1_extend)
        self.sell2 = Sell2Machine()
        self.sell4 = Sell4Machine(cfg.sell4_dip)
        self._buy3 = False
        self._buy4 = False
        self._sell1 = False
        self._sell2 = False
        self._sell4 = False
        self._peak: Decimal | None = None

    def observe(self, snap: MarketSnapshot) -> None:
        self._buy3 = self.buy3.update(snap.close, snap.ma)
        self._buy4 = self.buy4.update(snap.close, snap.ma, snap.ma_trend)
        self._sell1 = self.sell1.update(snap.close, snap.ma)
        self._sell2 = self.sell2.update(snap.close, snap.prev_close, snap.crossed_down)
        self._sell4 = self.sell4.update(snap.close, snap.ma)
        self._peak = self.sell4.last_peak or self.sell4.peak

    def evaluate(self, snap: MarketSnapshot, position: Position | None) -> Signal:
        self.observe(snap)
        same_entry = position is not None and snap.index == position.entry_candle_index
        if position is not None and not same_entry:
            sell = self._sell_signal(snap)
            if sell.kind != "HOLD":
                return sell
            tp = self._tp_signal(snap, position)
            if tp.kind != "HOLD":
                return tp
        if position is None:
            buy = self._buy_signal(snap)
            if buy.kind != "HOLD":
                return buy
        return Signal.hold()

    def _tp_signal(self, snap: MarketSnapshot, position: Position) -> Signal:
        target = pct_offset(position.average_price, position.tp_pct)
        if snap.close >= target:
            return Signal(
                kind="TP",
                side="sell",
                tp_pct=position.tp_pct,
                reason=(
                    f"take profit close={snap.close} >= "
                    f"{target} (fill_avg={position.average_price} + {position.tp_pct})"
                ),
            )
        return Signal.hold()

    def _sell_signal(self, snap: MarketSnapshot) -> Signal:
        if self._sell1:
            return Signal("SELL1", "sell", None, "price >=4% above MA then turned down")
        if self._sell2:
            return Signal(
                "SELL2",
                "sell",
                None,
                "price fell, crossed MA down, continued falling",
            )
        if snap.ma_trend == Trend.DOWN and snap.crossed_up:
            return Signal(
                "SELL3",
                "sell",
                None,
                "MA downtrend and price crossed MA upward",
                cross_price=snap.cross_price,
            )
        if self._sell4:
            return Signal(
                "SELL4",
                "sell",
                None,
                "failed recovery below MA; sell all at post-peak decline",
                peak_price=self._peak,
            )
        return Signal.hold()

    def _buy_signal(self, snap: MarketSnapshot) -> Signal:
        if (
            snap.prev_ma_trend == Trend.DOWN
            and snap.ma_trend in {Trend.FLAT, Trend.UP}
            and snap.crossed_up
        ):
            return Signal(
                "BUY1",
                "buy",
                self.cfg.buy1_tp,
                "MA left downtrend and price crossed above MA",
                cross_price=snap.cross_price,
            )
        if snap.ma_trend == Trend.UP and snap.crossed_down:
            tp = self.cfg.buy2_golden_tp if snap.golden_cross else self.cfg.buy2_tp
            return Signal(
                "BUY2",
                "buy",
                tp,
                "MA uptrend and price crossed below MA",
                golden_cross=snap.golden_cross,
                cross_price=snap.cross_price,
            )
        if self._buy3:
            return Signal("BUY3", "buy", self.cfg.buy3_tp, "pullback then bounce above MA")
        if self._buy4:
            return Signal(
                "BUY4",
                "buy",
                self.cfg.buy4_tp,
                "downtrend MA, price >=5% below, then rising",
            )
        return Signal.hold()


def build_snapshots(
    closes: Sequence[Decimal],
    timestamps: Sequence[int],
    cfg: Config,
) -> list[MarketSnapshot]:
    primary = moving_average(closes, cfg.ma_period, cfg.ma_kind)
    short = moving_average(closes, cfg.short_ma_period, cfg.ma_kind)
    long = moving_average(closes, cfg.long_ma_period, cfg.ma_kind)
    snaps: list[MarketSnapshot] = []
    prev_trend = Trend.FLAT
    start = max(cfg.ma_period, cfg.short_ma_period, cfg.long_ma_period)
    for i in range(start, len(closes)):
        ma = primary[i]
        prev_ma = primary[i - 1]
        s_ma = short[i]
        s_prev = short[i - 1]
        l_ma = long[i]
        l_prev = long[i - 1]
        if None in (ma, prev_ma, s_ma, s_prev, l_ma, l_prev):
            continue
        assert ma is not None and prev_ma is not None
        assert s_ma is not None and s_prev is not None
        assert l_ma is not None and l_prev is not None
        trend = ma_trend(ma, prev_ma, cfg.ma_slope_threshold)
        close = closes[i]
        prev_close = closes[i - 1]
        up = crossed_up(prev_close, prev_ma, close, ma)
        down = crossed_down(prev_close, prev_ma, close, ma)
        cross_price = None
        if up or down:
            cross_price = interpolate_crossover(prev_close, prev_ma, close, ma)
        snaps.append(
            MarketSnapshot(
                index=i,
                timestamp_ms=timestamps[i] if i < len(timestamps) else i,
                close=close,
                prev_close=prev_close,
                ma=ma,
                prev_ma=prev_ma,
                short_ma=s_ma,
                prev_short_ma=s_prev,
                long_ma=l_ma,
                prev_long_ma=l_prev,
                ma_trend=trend,
                prev_ma_trend=prev_trend,
                crossed_up=up,
                crossed_down=down,
                golden_cross=is_golden_cross(s_prev, l_prev, s_ma, l_ma),
                cross_price=cross_price,
            )
        )
        prev_trend = trend
    return snaps
