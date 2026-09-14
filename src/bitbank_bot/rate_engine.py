"""RateEngine: FIXED / DYNAMIC / AUTO take-profit and size policy.

Does not generate BUY/SELL. Strategy remains the only signal source.
README percents stay the FIXED baseline (BUY1 +3%, BUY2 +5%/+8%, BUY3 +4%, BUY4 +5%).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from bitbank_bot.config import Config
from bitbank_bot.indicators import Trend, atr as atr_series
from bitbank_bot.logging_setup import slog
from bitbank_bot.market_data import Candle
from bitbank_bot.money import D, ONE, ZERO
from bitbank_bot.strategy import Signal

REGIME_RANGE = "RANGE"
REGIME_TREND = "TREND"
REGIME_HIGH_VOL = "HIGH_VOLATILITY"
REGIME_UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RateDecision:
    mode: str
    take_profit_pct: Decimal | None
    stop_loss_pct: Decimal | None
    risk_pct: Decimal
    size_mult: Decimal
    reason: str
    market_regime: str
    atr: Decimal | None
    atr_pct: Decimal | None


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def last_atr(candles: list[Candle], period: int) -> Decimal | None:
    if period < 2 or len(candles) < period + 1:
        return None
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    series = atr_series(highs, lows, closes, period)
    value = series[-1]
    if value is None or value <= ZERO or value.is_nan() or value.is_infinite():
        return None
    return value


def detect_regime(atr_pct: Decimal | None, trend: Trend, cfg: Config) -> str:
    if atr_pct is None:
        return REGIME_UNKNOWN
    if atr_pct >= cfg.high_vol_atr_pct:
        return REGIME_HIGH_VOL
    if trend in {Trend.UP, Trend.DOWN}:
        return REGIME_TREND
    return REGIME_RANGE


def decide_rate(
    cfg: Config,
    signal: Signal,
    candles: list[Candle],
    trend: Trend,
    price: Decimal,
) -> RateDecision:
    atr_value = last_atr(candles, cfg.atr_period)
    atr_pct = (atr_value / price) if atr_value is not None and price > ZERO else None
    regime = detect_regime(atr_pct, trend, cfg)
    requested = cfg.rate_mode
    effective = requested
    size_mult = ONE
    reason = "fixed_readme_tp"
    if requested == "auto":
        if regime == REGIME_HIGH_VOL:
            effective = "dynamic"
            size_mult = cfg.high_vol_size_mult
            reason = "auto_high_vol_dynamic"
        elif regime == REGIME_TREND:
            effective = "dynamic"
            reason = "auto_trend_dynamic"
        else:
            effective = "fixed"
            reason = "auto_range_fixed"
    elif requested == "dynamic":
        reason = "dynamic_atr"
        if regime == REGIME_HIGH_VOL:
            size_mult = cfg.high_vol_size_mult
            reason = "dynamic_high_vol"

    base_tp = signal.tp_pct
    sl: Decimal | None = None
    risk = cfg.risk_pct
    tp = base_tp

    if effective == "dynamic":
        if atr_pct is None or atr_value is None:
            slog(
                "RATE",
                "EXECUTION_BLOCKED",
                reason="abnormal_atr",
                atr=str(atr_value) if atr_value is not None else None,
            )
            return RateDecision(
                mode="dynamic",
                take_profit_pct=base_tp,
                stop_loss_pct=None,
                risk_pct=risk,
                size_mult=ZERO,
                reason="abnormal_atr",
                market_regime=regime,
                atr=atr_value,
                atr_pct=atr_pct,
            )
        mid = cfg.atr_ref_pct if cfg.atr_ref_pct > ZERO else D("0.015")
        scale = _clamp(atr_pct / mid, D("0.5"), D("2.0"))
        if base_tp is not None:
            tp = _clamp(base_tp * scale, cfg.min_tp_pct, cfg.max_tp_pct)
        sl = _clamp(atr_pct * D("1.5"), cfg.min_sl_pct, cfg.max_sl_pct)
        risk = _clamp(cfg.risk_pct * (ONE / scale), cfg.min_risk_pct, cfg.max_risk_pct)

    slog(
        "RATE_DECIDED",
        "rate decision",
        requested=requested,
        mode=effective,
        regime=regime,
        tp=str(tp) if tp is not None else None,
        sl=str(sl) if sl is not None else None,
        risk_pct=str(risk),
        size_mult=str(size_mult),
        reason=reason,
        atr_pct=str(atr_pct) if atr_pct is not None else None,
    )
    return RateDecision(
        mode=effective,
        take_profit_pct=tp,
        stop_loss_pct=sl,
        risk_pct=risk,
        size_mult=size_mult,
        reason=reason,
        market_regime=regime,
        atr=atr_value,
        atr_pct=atr_pct,
    )


def apply_rate(signal: Signal, decision: RateDecision) -> Signal:
    if signal.side not in {"buy", "sell"}:
        return signal
    if decision.take_profit_pct is None or signal.tp_pct is None:
        return signal
    if decision.take_profit_pct == signal.tp_pct:
        return signal
    return Signal(
        kind=signal.kind,
        side=signal.side,
        tp_pct=decision.take_profit_pct,
        reason=f"{signal.reason}|rate={decision.reason}",
        golden_cross=signal.golden_cross,
        cross_price=signal.cross_price,
        peak_price=signal.peak_price,
        origin_price=signal.origin_price,
        crossover_price_bp=signal.crossover_price_bp,
        gates=signal.gates,
        score=signal.score,
        score_max=signal.score_max,
    )
