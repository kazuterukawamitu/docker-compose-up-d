"""FIXED / DYNAMIC / AUTO take-profit, stop-loss, and risk percentages.

Strategy still chooses BUY/SELL/HOLD. This module only sizes the rates.
Existing BUY1–4 take-profit percents stay the FIXED map.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from bitbank_bot.config import Config
from bitbank_bot.indicators import is_indicator_sane
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO
from bitbank_bot.strategy import MarketSnapshot, Signal


class RateMode(str, Enum):
    FIXED = "fixed"
    DYNAMIC = "dynamic"
    AUTO = "auto"


class MarketRegime(str, Enum):
    NORMAL = "NORMAL"
    TREND = "TREND"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    RANGE = "RANGE"


@dataclass(frozen=True)
class RateDecision:
    mode: RateMode
    take_profit_pct: Decimal
    stop_loss_pct: Decimal
    risk_pct: Decimal
    reason: str
    market_regime: MarketRegime
    valid: bool = True
    atr: Decimal | None = None
    atr_pct: Decimal | None = None
    adx: Decimal | None = None
    size_multiplier: Decimal = D("1")


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def detect_regime(cfg: Config, snap: MarketSnapshot) -> MarketRegime:
    atr_pct = snap.atr_pct
    adx = snap.adx
    if is_indicator_sane(atr_pct) and atr_pct is not None and atr_pct >= cfg.high_vol_atr_pct:
        return MarketRegime.HIGH_VOLATILITY
    if is_indicator_sane(adx) and adx is not None and adx >= cfg.adx_trend_threshold:
        return MarketRegime.TREND
    if is_indicator_sane(adx) and adx is not None and adx <= cfg.adx_range_threshold:
        return MarketRegime.RANGE
    return MarketRegime.NORMAL


def _fixed_from_signal(cfg: Config, signal: Signal) -> tuple[Decimal, str]:
    if signal.tp_pct is not None and signal.tp_pct > ZERO:
        return D(signal.tp_pct), f"fixed_tp_{signal.kind or 'signal'}"
    return D(cfg.buy1_tp), "fixed_tp_default_buy1"


def _dynamic_rates(
    cfg: Config, snap: MarketSnapshot, regime: MarketRegime
) -> RateDecision:
    atr = snap.atr
    price = snap.close
    if not is_indicator_sane(atr) or price <= ZERO:
        return RateDecision(
            RateMode.DYNAMIC,
            cfg.buy1_tp,
            cfg.default_sl_pct,
            cfg.default_risk_pct,
            "abnormal_atr",
            regime,
            valid=False,
            atr=atr,
            atr_pct=snap.atr_pct,
            adx=snap.adx,
        )
    assert atr is not None
    atr_pct = atr / price
    if not is_indicator_sane(atr_pct):
        return RateDecision(
            RateMode.DYNAMIC,
            cfg.buy1_tp,
            cfg.default_sl_pct,
            cfg.default_risk_pct,
            "abnormal_atr_pct",
            regime,
            valid=False,
            atr=atr,
            atr_pct=atr_pct,
            adx=snap.adx,
        )
    tp = _clamp(atr_pct * D("2.5"), cfg.min_tp_pct, cfg.max_tp_pct)
    sl = _clamp(atr_pct * D("1.2"), cfg.min_sl_pct, cfg.max_sl_pct)
    risk = cfg.default_risk_pct
    size_mult = D("1")
    reason = "dynamic_atr"
    if regime == MarketRegime.TREND:
        tp = _clamp(tp * D("1.5"), cfg.min_tp_pct, cfg.max_tp_pct)
        reason = "dynamic_trend_let_run"
    elif regime == MarketRegime.HIGH_VOLATILITY:
        tp = _clamp(tp * D("1.3"), cfg.min_tp_pct, cfg.max_tp_pct)
        sl = _clamp(sl * D("1.3"), cfg.min_sl_pct, cfg.max_sl_pct)
        size_mult = D("0.5")
        reason = "dynamic_high_vol_cut_size"
    elif is_indicator_sane(atr_pct) and atr_pct <= cfg.low_vol_atr_pct:
        tp = _clamp(tp * D("0.8"), cfg.min_tp_pct, cfg.max_tp_pct)
        sl = _clamp(sl * D("0.8"), cfg.min_sl_pct, cfg.max_sl_pct)
        reason = "dynamic_low_vol_tight"
    if cfg.low_vol_atr_pct > ZERO and atr_pct > ZERO:
        risk = _clamp(
            cfg.default_risk_pct * (cfg.low_vol_atr_pct / atr_pct),
            cfg.min_risk_pct,
            cfg.max_risk_pct,
        )
    return RateDecision(
        RateMode.DYNAMIC,
        tp,
        sl,
        risk,
        reason,
        regime,
        valid=True,
        atr=atr,
        atr_pct=atr_pct,
        adx=snap.adx,
        size_multiplier=size_mult,
    )


class RateEngine:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def decide(self, signal: Signal, snap: MarketSnapshot | None) -> RateDecision:
        requested = RateMode(self.cfg.rate_mode)
        regime = detect_regime(self.cfg, snap) if snap is not None else MarketRegime.NORMAL
        if requested == RateMode.AUTO:
            if regime in {MarketRegime.TREND, MarketRegime.HIGH_VOLATILITY}:
                used = RateMode.DYNAMIC
            else:
                used = RateMode.FIXED
        else:
            used = requested
        if used == RateMode.FIXED or snap is None:
            tp, reason = _fixed_from_signal(self.cfg, signal)
            decision = RateDecision(
                RateMode.FIXED,
                tp,
                self.cfg.default_sl_pct,
                self.cfg.default_risk_pct,
                reason if requested == RateMode.FIXED else f"auto_{regime.value.lower()}_fixed",
                regime,
                valid=True,
                atr=snap.atr if snap else None,
                atr_pct=snap.atr_pct if snap else None,
                adx=snap.adx if snap else None,
            )
        else:
            decision = _dynamic_rates(self.cfg, snap, regime)
        slog(
            "RATE_DECIDED",
            "rate decision",
            requested=requested.value,
            mode=decision.mode.value,
            take_profit_pct=str(decision.take_profit_pct),
            stop_loss_pct=str(decision.stop_loss_pct),
            risk_pct=str(decision.risk_pct),
            reason=decision.reason,
            market_regime=decision.market_regime.value,
            valid=decision.valid,
            size_multiplier=str(decision.size_multiplier),
        )
        return decision
