"""FIXED / DYNAMIC / AUTO take-profit, stop-loss, and risk percentages.

Strategy still owns BUY/SELL/HOLD and the README fixed TP map
(BUY1 +3%, BUY2 +5%/+8%, BUY3 +4%, BUY4 +5%). This engine only
converts those into a RateDecision and never places an order.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from bitbank_bot.config import Config
from bitbank_bot.indicators import adx, atr, last_valid, realized_vol
from bitbank_bot.logging_setup import slog
from bitbank_bot.market_data import Candle
from bitbank_bot.money import D, ZERO
from bitbank_bot.strategy import Signal

REGIME_NORMAL = "NORMAL"
REGIME_TREND = "TREND"
REGIME_HIGH_VOL = "HIGH_VOLATILITY"
REGIME_RANGE = "RANGE"


@dataclass(frozen=True)
class MarketMetrics:
    atr: Decimal | None
    atr_pct: Decimal | None
    adx: Decimal | None
    realized_vol: Decimal | None
    ok: bool
    reason: str


@dataclass(frozen=True)
class RateDecision:
    mode: str
    take_profit_pct: Decimal
    stop_loss_pct: Decimal
    risk_pct: Decimal
    reason: str
    market_regime: str
    size_scale: Decimal
    ok: bool
    atr_pct: Decimal | None
    adx: Decimal | None


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def measure_market(candles: Sequence[Candle], cfg: Config) -> MarketMetrics:
    if len(candles) < max(cfg.atr_period, cfg.adx_period) + 2:
        return MarketMetrics(None, None, None, None, False, "not_enough_candles_for_atr")
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    atr_v = last_valid(atr(highs, lows, closes, cfg.atr_period))
    adx_v = last_valid(adx(highs, lows, closes, cfg.adx_period))
    vol = realized_vol(closes, min(20, len(closes) - 1))
    price = closes[-1]
    if atr_v is None or price <= ZERO or atr_v <= ZERO:
        return MarketMetrics(atr_v, None, adx_v, vol, False, "abnormal_atr")
    atr_pct = atr_v / price
    if atr_pct.is_nan() or atr_pct.is_infinite() or atr_pct <= ZERO:
        return MarketMetrics(atr_v, atr_pct, adx_v, vol, False, "abnormal_atr")
    return MarketMetrics(atr_v, atr_pct, adx_v, vol, True, "ok")


def detect_regime(metrics: MarketMetrics, cfg: Config) -> str:
    if not metrics.ok or metrics.atr_pct is None:
        return REGIME_NORMAL
    if metrics.atr_pct >= cfg.high_vol_atr_pct:
        return REGIME_HIGH_VOL
    if metrics.adx is not None and metrics.adx >= cfg.trend_adx:
        return REGIME_TREND
    if metrics.adx is not None and metrics.adx <= cfg.range_adx:
        return REGIME_RANGE
    return REGIME_NORMAL


def _fixed_tp(signal: Signal, cfg: Config) -> Decimal:
    if signal.tp_pct is not None and signal.tp_pct > ZERO:
        return D(signal.tp_pct)
    return cfg.buy1_tp


def _fixed_decision(signal: Signal, cfg: Config, regime: str, metrics: MarketMetrics) -> RateDecision:
    tp = _clamp(_fixed_tp(signal, cfg), cfg.min_tp_pct, cfg.max_tp_pct)
    sl = _clamp(tp / D(2), cfg.min_sl_pct, cfg.max_sl_pct)
    return RateDecision(
        mode="FIXED",
        take_profit_pct=tp,
        stop_loss_pct=sl,
        risk_pct=_clamp(cfg.default_risk_pct, cfg.min_risk_pct, cfg.max_risk_pct),
        reason=f"fixed_map kind={signal.kind}",
        market_regime=regime,
        size_scale=D("1"),
        ok=True,
        atr_pct=metrics.atr_pct,
        adx=metrics.adx,
    )


def _dynamic_decision(
    signal: Signal,
    cfg: Config,
    regime: str,
    metrics: MarketMetrics,
    *,
    size_scale: Decimal | None = None,
) -> RateDecision:
    if not metrics.ok or metrics.atr_pct is None:
        return RateDecision(
            mode="DYNAMIC",
            take_profit_pct=cfg.min_tp_pct,
            stop_loss_pct=cfg.min_sl_pct,
            risk_pct=cfg.min_risk_pct,
            reason=metrics.reason,
            market_regime=regime,
            size_scale=D("0"),
            ok=False,
            atr_pct=metrics.atr_pct,
            adx=metrics.adx,
        )
    base_tp = _fixed_tp(signal, cfg)
    mid = D("0.01")
    vol_scale = metrics.atr_pct / mid
    tp = _clamp(base_tp * vol_scale, cfg.min_tp_pct, cfg.max_tp_pct)
    if regime == REGIME_TREND:
        tp = _clamp(tp * D("1.25"), cfg.min_tp_pct, cfg.max_tp_pct)
    sl = _clamp(max(metrics.atr_pct, base_tp / D(2)), cfg.min_sl_pct, cfg.max_sl_pct)
    risk = _clamp(cfg.default_risk_pct / max(vol_scale, D("0.5")), cfg.min_risk_pct, cfg.max_risk_pct)
    scale = size_scale if size_scale is not None else D("1")
    if regime == REGIME_HIGH_VOL:
        scale = min(scale, cfg.dynamic_size_scale)
    return RateDecision(
        mode="DYNAMIC",
        take_profit_pct=tp,
        stop_loss_pct=sl,
        risk_pct=risk,
        reason=f"dynamic atr_pct={metrics.atr_pct} adx={metrics.adx}",
        market_regime=regime,
        size_scale=scale,
        ok=True,
        atr_pct=metrics.atr_pct,
        adx=metrics.adx,
    )


class RateEngine:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def decide(self, signal: Signal, candles: Sequence[Candle]) -> RateDecision:
        metrics = measure_market(candles, self.cfg)
        regime = detect_regime(metrics, self.cfg)
        requested = self.cfg.rate_mode
        if requested == "auto":
            if regime == REGIME_HIGH_VOL:
                decision = _dynamic_decision(
                    signal, self.cfg, regime, metrics, size_scale=self.cfg.dynamic_size_scale
                )
            elif regime == REGIME_TREND:
                decision = _dynamic_decision(signal, self.cfg, regime, metrics)
            elif regime == REGIME_RANGE and self.cfg.range_suppress_trades:
                decision = RateDecision(
                    mode="FIXED",
                    take_profit_pct=self.cfg.min_tp_pct,
                    stop_loss_pct=self.cfg.min_sl_pct,
                    risk_pct=self.cfg.min_risk_pct,
                    reason="range_suppress_trades",
                    market_regime=regime,
                    size_scale=D("0"),
                    ok=False,
                    atr_pct=metrics.atr_pct,
                    adx=metrics.adx,
                )
            else:
                decision = _fixed_decision(signal, self.cfg, regime, metrics)
        elif requested == "dynamic":
            decision = _dynamic_decision(signal, self.cfg, regime, metrics)
        else:
            decision = _fixed_decision(signal, self.cfg, regime, metrics)
        slog(
            "RATE_DECIDED",
            "rate decision",
            mode=decision.mode,
            requested=requested,
            take_profit_pct=str(decision.take_profit_pct),
            stop_loss_pct=str(decision.stop_loss_pct),
            risk_pct=str(decision.risk_pct),
            market_regime=decision.market_regime,
            reason=decision.reason,
            ok=decision.ok,
        )
        return decision
