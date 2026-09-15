"""FIXED / DYNAMIC / AUTO take-profit and risk overlay.

Strategy still owns BUY1–4 percents. This module only rescales them when
RATE_MODE is dynamic or auto. Invalid ATR never invents a rate; it blocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from bitbank_bot.config import Config
from bitbank_bot.indicators import Trend
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ONE, ZERO
from bitbank_bot.strategy import Signal


@dataclass(frozen=True)
class RateDecision:
    mode: str
    take_profit_pct: Decimal | None
    stop_loss_pct: Decimal | None
    risk_pct: Decimal
    size_mult: Decimal
    reason: str
    market_regime: str
    allow_trade: bool = True


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _regime(trend: Trend, vol: Decimal, cfg: Config) -> str:
    if vol >= cfg.vol_high:
        return "HIGH_VOLATILITY"
    if trend in {Trend.UP, Trend.DOWN}:
        return "TREND"
    if vol <= cfg.vol_low:
        return "RANGE"
    return "NORMAL"


def decide(
    cfg: Config,
    signal: Signal,
    *,
    atr: Decimal | None,
    price: Decimal,
    trend: Trend,
) -> RateDecision:
    base_tp = signal.tp_pct if signal.tp_pct is not None else cfg.buy1_tp
    vol = ZERO
    if atr is not None and price > ZERO:
        vol = D(atr) / D(price)
    regime = _regime(trend, vol, cfg)
    mode = cfg.rate_mode
    if mode == "auto":
        if regime in {"TREND", "HIGH_VOLATILITY"}:
            mode = "dynamic"
        else:
            mode = "fixed"

    if mode == "fixed":
        decision = RateDecision(
            mode="fixed",
            take_profit_pct=base_tp,
            stop_loss_pct=None,
            risk_pct=cfg.default_risk_pct,
            size_mult=ONE,
            reason=f"fixed_strategy_tp regime={regime}",
            market_regime=regime,
            allow_trade=True,
        )
        slog(
            "RATE_DECIDED",
            "fixed",
            mode=decision.mode,
            take_profit_pct=str(decision.take_profit_pct),
            market_regime=regime,
            reason=decision.reason,
        )
        return decision

    if atr is None or atr <= ZERO or price <= ZERO:
        slog("RATE_DECIDED", "blocked", reason="atr_invalid", market_regime=regime)
        return RateDecision(
            mode="dynamic",
            take_profit_pct=None,
            stop_loss_pct=None,
            risk_pct=cfg.default_risk_pct,
            size_mult=ZERO,
            reason="atr_invalid",
            market_regime=regime,
            allow_trade=False,
        )

    ref = cfg.vol_low if cfg.vol_low > ZERO else D("0.005")
    scale = vol / ref if ref > ZERO else ONE
    tp = _clamp(base_tp * scale, cfg.min_tp_pct, cfg.max_tp_pct)
    sl = _clamp(cfg.default_sl_pct * scale, cfg.min_sl_pct, cfg.max_sl_pct)
    risk_pct = _clamp(cfg.default_risk_pct, cfg.min_risk_pct, cfg.max_risk_pct)
    size_mult = cfg.high_vol_size_mult if regime == "HIGH_VOLATILITY" else ONE
    decision = RateDecision(
        mode="dynamic",
        take_profit_pct=tp,
        stop_loss_pct=sl,
        risk_pct=risk_pct,
        size_mult=size_mult,
        reason=f"dynamic vol={vol} scale={scale}",
        market_regime=regime,
        allow_trade=True,
    )
    slog(
        "RATE_DECIDED",
        "dynamic",
        mode=decision.mode,
        take_profit_pct=str(decision.take_profit_pct),
        stop_loss_pct=str(decision.stop_loss_pct),
        risk_pct=str(decision.risk_pct),
        size_mult=str(decision.size_mult),
        market_regime=regime,
        reason=decision.reason,
    )
    return decision
