"""FIXED / DYNAMIC / AUTO take-profit, stop, and risk percentages.

FIXED preserves the README per-strategy mappings (BUY1 +3%, BUY3 +4%,
BUY2 +5%, BUY2 golden +8%, BUY4 +5%). DYNAMIC uses ATR/ADX/vol with clamps.
AUTO picks a regime; it never invents new FIXED percents.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from bitbank_bot.config import (
    RATE_MODE_AUTO,
    RATE_MODE_DYNAMIC,
    RATE_MODE_FIXED,
    RANGE_ACTION_SUPPRESS,
    Config,
)
from bitbank_bot.indicators import (
    adx,
    atr,
    atr_is_abnormal,
    last_defined,
    realized_vol,
)
from bitbank_bot.logging_setup import slog
from bitbank_bot.market_data import Candle
from bitbank_bot.money import D, ZERO
from bitbank_bot.strategy import Signal


class MarketRegime(str, Enum):
    NORMAL = "NORMAL"
    TREND = "TREND"
    HIGH_VOL = "HIGH_VOL"
    RANGE = "RANGE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RateDecision:
    mode: str
    take_profit_pct: Decimal | None
    stop_loss_pct: Decimal | None
    risk_pct: Decimal
    reason: str
    market_regime: MarketRegime
    size_mult: Decimal
    atr_value: Decimal | None
    atr_pct: Decimal | None
    adx_value: Decimal | None
    suppress: bool = False


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _fixed_tp(signal: Signal, cfg: Config) -> Decimal | None:
    if signal.tp_pct is not None:
        return D(signal.tp_pct)
    mapping = {
        "BUY1": cfg.buy1_tp,
        "BUY2": cfg.buy2_golden_tp if signal.golden_cross else cfg.buy2_tp,
        "BUY3": cfg.buy3_tp,
        "BUY4": cfg.buy4_tp,
        "TP": signal.tp_pct,
    }
    return mapping.get(signal.kind)


def classify_regime(
    *,
    atr_pct: Decimal | None,
    adx_value: Decimal | None,
    cfg: Config,
) -> MarketRegime:
    if atr_pct is not None and atr_pct >= cfg.high_vol_atr_pct:
        return MarketRegime.HIGH_VOL
    if adx_value is not None and adx_value >= cfg.adx_trend_threshold:
        return MarketRegime.TREND
    if adx_value is not None and adx_value < cfg.range_adx_threshold:
        return MarketRegime.RANGE
    if atr_pct is None and adx_value is None:
        return MarketRegime.UNKNOWN
    return MarketRegime.NORMAL


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
        cfg = self.cfg
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        closes = [c.close for c in candles]
        price = closes[-1] if closes else ZERO
        atr_series = atr(highs, lows, closes, cfg.atr_period) if candles else []
        adx_series = adx(highs, lows, closes, cfg.adx_period) if candles else []
        atr_value = last_defined(atr_series)
        adx_value = last_defined(adx_series)
        vol = realized_vol(closes, cfg.atr_period)
        atr_pct = (atr_value / price) if atr_value is not None and price > ZERO else None
        if stale:
            slog("RATE", "stale data; no DYNAMIC calc", reason="stale_market_data")
            tp = _fixed_tp(signal, cfg)
            return RateDecision(
                RATE_MODE_FIXED,
                tp,
                None,
                cfg.default_risk_pct,
                "stale_no_dynamic",
                MarketRegime.UNKNOWN,
                D(1),
                atr_value,
                atr_pct,
                adx_value,
                suppress=True,
            )
        if atr_is_abnormal(atr_value, price, cfg.abnormal_atr_pct):
            slog(
                "RATE",
                "abnormal ATR; no orders",
                atr=str(atr_value) if atr_value is not None else None,
            )
            return RateDecision(
                cfg.rate_mode,
                _fixed_tp(signal, cfg),
                None,
                cfg.min_risk_pct,
                "abnormal_atr",
                MarketRegime.UNKNOWN,
                D(1),
                atr_value,
                atr_pct,
                adx_value,
                suppress=True,
            )
        regime = classify_regime(atr_pct=atr_pct, adx_value=adx_value, cfg=cfg)
        requested = cfg.rate_mode
        mode = requested
        size_mult = D(1)
        suppress = False
        if requested == RATE_MODE_AUTO:
            if regime == MarketRegime.HIGH_VOL:
                mode = RATE_MODE_DYNAMIC
                size_mult = cfg.high_vol_size_mult
            elif regime == MarketRegime.TREND:
                mode = RATE_MODE_DYNAMIC
            elif regime == MarketRegime.RANGE:
                if cfg.range_action == RANGE_ACTION_SUPPRESS:
                    mode = RATE_MODE_FIXED
                    suppress = True
                else:
                    mode = RATE_MODE_FIXED
            else:
                mode = RATE_MODE_FIXED
        if mode == RATE_MODE_DYNAMIC:
            if atr_pct is None:
                mode = RATE_MODE_FIXED
                reason = "dynamic_missing_atr_fallback_fixed"
                tp = _fixed_tp(signal, cfg)
                sl = None
                risk = cfg.default_risk_pct
            else:
                vol_term = vol if vol is not None else ZERO
                raw_tp = atr_pct * cfg.atr_tp_mult + vol_term
                raw_sl = atr_pct * cfg.atr_sl_mult
                tp = _clamp(raw_tp, cfg.min_tp_pct, cfg.max_tp_pct)
                sl = _clamp(raw_sl, cfg.min_sl_pct, cfg.max_sl_pct)
                risk = _clamp(cfg.default_risk_pct, cfg.min_risk_pct, cfg.max_risk_pct)
                risk = min(risk, cfg.max_risk_per_trade)
                if regime == MarketRegime.HIGH_VOL:
                    risk = min(risk, cfg.min_risk_pct)
                reason = f"dynamic_atr regime={regime.value}"
        else:
            tp = _fixed_tp(signal, cfg)
            sl = None
            risk = _clamp(cfg.default_risk_pct, cfg.min_risk_pct, cfg.max_risk_pct)
            reason = f"fixed_strategy_tp regime={regime.value}"
        risk = min(risk, cfg.max_risk_per_trade, cfg.max_risk_pct)
        decision = RateDecision(
            mode,
            tp,
            sl,
            risk,
            reason,
            regime,
            size_mult,
            atr_value,
            atr_pct,
            adx_value,
            suppress=suppress,
        )
        slog(
            "RATE_DECIDED",
            "rate decision",
            mode=decision.mode,
            take_profit_pct=str(decision.take_profit_pct)
            if decision.take_profit_pct is not None
            else None,
            stop_loss_pct=str(decision.stop_loss_pct)
            if decision.stop_loss_pct is not None
            else None,
            risk_pct=str(decision.risk_pct),
            reason=decision.reason,
            market_regime=decision.market_regime.value,
            size_mult=str(decision.size_mult),
        )
        return decision
