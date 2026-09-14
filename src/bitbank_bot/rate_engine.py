"""FIXED / DYNAMIC / AUTO take-profit and size multipliers.

FIXED keeps README TPs (3/4/5/8%). DYNAMIC only widens/narrows from ATR
and clamps. Strategy code does not call Bitbank.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from bitbank_bot.config import Config
from bitbank_bot.indicators import Trend, atr as atr_series
from bitbank_bot.logging_setup import slog
from bitbank_bot.market_data import Candle
from bitbank_bot.money import D, ONE, ZERO
from bitbank_bot.strategy import Signal

MIN_TP_PCT = D("0.02")
MAX_TP_PCT = D("0.12")
MIN_SL_PCT = D("0.01")
MAX_SL_PCT = D("0.08")
MIN_RISK_PCT = D("0.002")
MAX_RISK_PCT = D("0.02")
ATR_PERIOD = 14
HIGH_VOL_ATR_PCT = D("0.03")
LOW_VOL_ATR_PCT = D("0.008")
DEFAULT_RISK_PCT = D("0.01")
DEFAULT_SL_PCT = D("0.02")


@dataclass(frozen=True)
class RateDecision:
    mode: str
    take_profit_pct: Decimal | None
    stop_loss_pct: Decimal | None
    risk_pct: Decimal
    size_mult: Decimal
    reason: str
    market_regime: str


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _atr_pct(candles: Sequence[Candle], price: Decimal) -> Decimal | None:
    if price <= ZERO or len(candles) < ATR_PERIOD + 2:
        return None
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    value = atr_series(highs, lows, closes, ATR_PERIOD)
    if value is None or value <= ZERO:
        return None
    return value / price


def _regime(trend: str, atr_pct: Decimal | None) -> str:
    if atr_pct is None:
        return "UNKNOWN"
    if atr_pct >= HIGH_VOL_ATR_PCT:
        return "HIGH_VOLATILITY"
    label = (trend or "").upper()
    if label == Trend.UP.value or label == Trend.DOWN.value:
        return "TREND"
    if atr_pct <= LOW_VOL_ATR_PCT:
        return "RANGE"
    return "NORMAL"


def decide(
    cfg: Config,
    signal: Signal,
    *,
    price: Decimal,
    candles: Sequence[Candle],
    trend: str = "",
) -> RateDecision:
    atr_pct = _atr_pct(candles, D(price))
    regime = _regime(trend, atr_pct)
    mode = (cfg.rate_mode or "fixed").lower()
    base_tp = signal.tp_pct
    if mode == "auto":
        if regime in {"TREND", "HIGH_VOLATILITY"}:
            mode = "dynamic"
            reason = f"auto->{mode}/{regime}"
        else:
            mode = "fixed"
            reason = f"auto->{mode}/{regime}"
    elif mode == "dynamic":
        reason = f"dynamic/{regime}"
    else:
        mode = "fixed"
        reason = f"fixed/{regime}"

    sl = _clamp(DEFAULT_SL_PCT, MIN_SL_PCT, MAX_SL_PCT)
    risk = _clamp(DEFAULT_RISK_PCT, MIN_RISK_PCT, MAX_RISK_PCT)
    size_mult = ONE

    if mode == "dynamic":
        if atr_pct is None or atr_pct <= ZERO:
            slog(
                "RATE_DECIDED",
                "dynamic missing ATR; using FIXED tps",
                reason="atr_unavailable",
            )
            mode = "fixed"
            reason = "dynamic_fallback_fixed"
        else:
            raw_tp = _clamp(atr_pct * D("2"), MIN_TP_PCT, MAX_TP_PCT)
            sl = _clamp(atr_pct, MIN_SL_PCT, MAX_SL_PCT)
            if atr_pct >= HIGH_VOL_ATR_PCT:
                size_mult = _clamp(HIGH_VOL_ATR_PCT / atr_pct, D("0.25"), ONE)
                risk = _clamp(DEFAULT_RISK_PCT * size_mult, MIN_RISK_PCT, MAX_RISK_PCT)
            base_tp = raw_tp if signal.side == "buy" else signal.tp_pct

    decision = RateDecision(
        mode=mode,
        take_profit_pct=base_tp,
        stop_loss_pct=sl if mode == "dynamic" else None,
        risk_pct=risk,
        size_mult=size_mult,
        reason=reason,
        market_regime=regime,
    )
    slog(
        "RATE_DECIDED",
        "rate decision",
        mode=decision.mode,
        take_profit_pct=str(decision.take_profit_pct or ""),
        size_mult=str(decision.size_mult),
        reason=decision.reason,
        market_regime=decision.market_regime,
    )
    return decision
