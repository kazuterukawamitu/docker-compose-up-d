"""FIXED / DYNAMIC / AUTO rate policy. Strategy TPs stay 3/4/5/8% in FIXED."""

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

REGIME_NORMAL = "NORMAL"
REGIME_TREND = "TREND"
REGIME_HIGH_VOLATILITY = "HIGH_VOLATILITY"
REGIME_RANGE = "RANGE"
TREND_MOVE_PCT = D("0.03")


@dataclass(frozen=True)
class RateDecision:
    mode: str
    take_profit_pct: Decimal | None
    ok: bool
    reason: str
    atr_value: Decimal | None
    size_mult: Decimal
    stop_loss_pct: Decimal | None = None
    risk_pct: Decimal | None = None
    market_regime: str = REGIME_NORMAL


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


def _atr_pct(atr_value: Decimal, candles: list[Candle]) -> Decimal | None:
    close = candles[-1].close
    if close <= ZERO:
        return None
    pct = atr_value / close
    if pct <= ZERO or pct.is_nan() or pct.is_infinite():
        return None
    return pct


def _regime(atr_pct: Decimal, candles: list[Candle], cfg: Config) -> str:
    if atr_pct >= cfg.high_vol_atr_pct:
        return REGIME_HIGH_VOLATILITY
    if atr_pct <= cfg.low_vol_atr_pct:
        return REGIME_RANGE
    if len(candles) >= 21:
        prev = candles[-21].close
        if prev > ZERO:
            move = abs(candles[-1].close - prev) / prev
            if move >= TREND_MOVE_PCT:
                return REGIME_TREND
    return REGIME_NORMAL


def _dynamic_params(
    tp: Decimal | None,
    atr_pct: Decimal,
    cfg: Config,
    regime: str,
) -> tuple[Decimal | None, Decimal, Decimal, Decimal]:
    baseline = cfg.atr_baseline_pct if cfg.atr_baseline_pct > ZERO else D("0.01")
    scale = atr_pct / baseline
    dyn_tp = _clamp(tp * scale, cfg.min_tp_pct, cfg.max_tp_pct) if tp is not None else None
    sl = _clamp(atr_pct * D("1.5"), cfg.min_sl_pct, cfg.max_sl_pct)
    size_mult = cfg.high_vol_size_mult if regime == REGIME_HIGH_VOLATILITY else D(1)
    if size_mult <= ZERO or size_mult > D(1):
        size_mult = D("0.5") if regime == REGIME_HIGH_VOLATILITY else D(1)
    risk = _clamp(cfg.max_balance_usage * size_mult, cfg.min_risk_pct, cfg.max_risk_pct)
    return dyn_tp, sl, risk, size_mult


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
            risk = _clamp(self.cfg.max_balance_usage, self.cfg.min_risk_pct, self.cfg.max_risk_pct)
            return RateDecision(
                RATE_MODE_FIXED,
                tp,
                True,
                "fixed_strategy_tp",
                atr_value,
                D(1),
                stop_loss_pct=self.cfg.min_sl_pct,
                risk_pct=risk,
                market_regime=REGIME_NORMAL,
            )
        if stale or atr_bad:
            reason = "stale_data" if stale else "atr_unavailable"
            slog("RATE", "DYNAMIC halted", reason=reason, rate_mode=requested)
            if requested == RATE_MODE_DYNAMIC:
                return RateDecision(
                    RATE_MODE_DYNAMIC, tp, False, reason, atr_value, D(1)
                )
            risk = _clamp(self.cfg.max_balance_usage, self.cfg.min_risk_pct, self.cfg.max_risk_pct)
            return RateDecision(
                RATE_MODE_FIXED,
                tp,
                True,
                "auto_fallback_fixed",
                atr_value,
                D(1),
                stop_loss_pct=self.cfg.min_sl_pct,
                risk_pct=risk,
                market_regime=REGIME_NORMAL,
            )
        atr_pct = _atr_pct(atr_value, candles)
        if atr_pct is None:
            slog("RATE", "DYNAMIC halted", reason="atr_unavailable", rate_mode=requested)
            if requested == RATE_MODE_DYNAMIC:
                return RateDecision(
                    RATE_MODE_DYNAMIC, tp, False, "atr_unavailable", atr_value, D(1)
                )
            return RateDecision(RATE_MODE_FIXED, tp, True, "auto_fallback_fixed", atr_value, D(1))
        regime = _regime(atr_pct, candles, self.cfg)
        use_dynamic = requested == RATE_MODE_DYNAMIC or (
            requested == RATE_MODE_AUTO and regime in {REGIME_TREND, REGIME_HIGH_VOLATILITY}
        )
        if not use_dynamic:
            risk = _clamp(self.cfg.max_balance_usage, self.cfg.min_risk_pct, self.cfg.max_risk_pct)
            slog("RATE", "AUTO fixed", regime=regime, atr_pct=str(atr_pct))
            return RateDecision(
                RATE_MODE_FIXED,
                tp,
                True,
                f"auto_{regime.lower()}_fixed",
                atr_value,
                D(1),
                stop_loss_pct=self.cfg.min_sl_pct,
                risk_pct=risk,
                market_regime=regime,
            )
        dyn_tp, sl, risk, size_mult = _dynamic_params(tp, atr_pct, self.cfg, regime)
        reason = "ok" if requested == RATE_MODE_DYNAMIC else f"auto_{regime.lower()}"
        slog(
            "RATE_DECIDED",
            "DYNAMIC ok",
            atr=str(atr_value),
            atr_pct=str(atr_pct),
            tp=str(dyn_tp) if dyn_tp is not None else None,
            sl=str(sl),
            size_mult=str(size_mult),
            regime=regime,
            rate_mode=requested,
        )
        return RateDecision(
            requested if requested == RATE_MODE_DYNAMIC else RATE_MODE_DYNAMIC,
            dyn_tp,
            True,
            reason,
            atr_value,
            size_mult,
            stop_loss_pct=sl,
            risk_pct=risk,
            market_regime=regime,
        )
