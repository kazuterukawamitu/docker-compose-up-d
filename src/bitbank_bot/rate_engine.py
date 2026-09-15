"""FIXED / DYNAMIC / AUTO rate policy. Strategy TPs stay 3/4/5/8%."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from bitbank_bot.config import (
    RATE_MODE_AUTO,
    RATE_MODE_DYNAMIC,
    RATE_MODE_FIXED,
    Config,
)
from bitbank_bot.indicators import atr
from bitbank_bot.logging_setup import slog
from bitbank_bot.market_data import Candle
from bitbank_bot.money import D, ZERO
from bitbank_bot.strategy import Signal


@dataclass(frozen=True)
class RateDecision:
    mode: str
    take_profit_pct: Decimal | None
    ok: bool
    reason: str
    atr_value: Decimal | None
    size_mult: Decimal


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _strategy_tp(signal: Signal, cfg: Config) -> Decimal | None:
    if signal.tp_pct is not None:
        return D(signal.tp_pct)
    mapping = {
        "BUY1": cfg.buy1_tp,
        "BUY2": cfg.buy2_golden_tp if signal.golden_cross else cfg.buy2_tp,
        "BUY3": cfg.buy3_tp,
        "BUY4": cfg.buy4_tp,
    }
    return mapping.get(signal.kind)


class RateEngine:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def decide(
        self,
        signal: Signal,
        candles: list[Candle],
        *,
        stale: bool = False,
    ) -> RateDecision:
        tp = _strategy_tp(signal, self.cfg)
        if tp is not None:
            tp = _clamp(tp, self.cfg.min_tp_pct, self.cfg.max_tp_pct)
        requested = self.cfg.rate_mode
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        atr_value = atr(highs, lows, closes, self.cfg.atr_period) if candles else None
        atr_bad = atr_value is None or atr_value <= ZERO
        if requested == RATE_MODE_FIXED:
            return RateDecision(RATE_MODE_FIXED, tp, True, "fixed_strategy_tp", atr_value, D(1))
        if stale or atr_bad:
            reason = "stale_data" if stale else "atr_unavailable"
            slog("RATE", "DYNAMIC halted", reason=reason, rate_mode=requested)
            if requested == RATE_MODE_DYNAMIC:
                return RateDecision(RATE_MODE_DYNAMIC, tp, False, reason, atr_value, D(1))
            return RateDecision(RATE_MODE_FIXED, tp, True, "auto_fallback_fixed", atr_value, D(1))
        slog("RATE", "DYNAMIC ok", atr=str(atr_value), tp=str(tp) if tp is not None else None)
        return RateDecision(requested, tp, True, "ok", atr_value, D(1))
