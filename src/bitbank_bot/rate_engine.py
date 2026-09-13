"""FIXED / DYNAMIC / AUTO take-profit, stop-loss, and risk percentages.

Strategies still choose BUY/SELL/HOLD and keep their README take-profit
mapping (BUY1 +3%, BUY2 +5%/+8%, BUY3 +4%, BUY4 +5%). This module only
decides which percentages the sizer and exit logic use.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from bitbank_bot.config import Config
from bitbank_bot.indicators import adx, atr, last_defined, realized_vol_pct
from bitbank_bot.logging_setup import slog
from bitbank_bot.market_data import Candle
from bitbank_bot.money import D, ONE, ZERO
from bitbank_bot.strategy import Signal

REGIME_NORMAL = "NORMAL"
REGIME_TREND = "TREND"
REGIME_HIGH_VOLATILITY = "HIGH_VOLATILITY"
REGIME_RANGE = "RANGE"


@dataclass(frozen=True)
class RateDecision:
    mode: str
    requested_mode: str
    take_profit_pct: Decimal
    stop_loss_pct: Decimal
    risk_pct: Decimal
    reason: str
    market_regime: str
    position_scale: Decimal = ONE
    atr: Decimal | None = None
    atr_pct: Decimal | None = None
    adx: Decimal | None = None
    realized_vol_pct: Decimal | None = None
    ok: bool = True


def _clamp(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    if value < low:
        return low
    if value > high:
        return high
    return value


def detect_regime(
    cfg: Config,
    *,
    atr_pct: Decimal | None,
    adx_value: Decimal | None,
) -> str:
    if atr_pct is not None and atr_pct >= cfg.regime_atr_high:
        return REGIME_HIGH_VOLATILITY
    if adx_value is not None and adx_value >= cfg.regime_adx_trend:
        return REGIME_TREND
    if adx_value is not None and adx_value <= cfg.regime_adx_range:
        return REGIME_RANGE
    return REGIME_NORMAL


def _metrics(candles: Sequence[Candle], cfg: Config) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None]:
    if len(candles) < max(cfg.atr_period, cfg.adx_period) + 1:
        return None, None, None, None
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    atr_value = last_defined(atr(highs, lows, closes, cfg.atr_period))
    adx_value = last_defined(adx(highs, lows, closes, cfg.adx_period))
    vol = realized_vol_pct(closes, cfg.atr_period)
    price = closes[-1]
    atr_pct = (atr_value / price) if atr_value is not None and price > ZERO else None
    return atr_value, atr_pct, adx_value, vol


def _fixed_tp(signal: Signal, cfg: Config) -> Decimal:
    if signal.tp_pct is not None and signal.tp_pct > ZERO:
        return signal.tp_pct
    return cfg.buy1_tp


class RateEngine:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def decide(
        self,
        signal: Signal,
        candles: Sequence[Candle],
        *,
        price: Decimal | None = None,
    ) -> RateDecision:
        requested = (self.cfg.rate_mode or "fixed").lower()
        atr_value, atr_pct, adx_value, vol = _metrics(candles, self.cfg)
        regime = detect_regime(self.cfg, atr_pct=atr_pct, adx_value=adx_value)
        slog(
            "RATE_DECIDED",
            "market regime",
            requested_mode=requested,
            regime=regime,
            atr=str(atr_value) if atr_value is not None else None,
            atr_pct=str(atr_pct) if atr_pct is not None else None,
            adx=str(adx_value) if adx_value is not None else None,
            realized_vol=str(vol) if vol is not None else None,
        )
        if requested == "auto":
            if regime == REGIME_HIGH_VOLATILITY:
                return self._dynamic(
                    signal, requested, regime, atr_value, atr_pct, adx_value, vol,
                    position_scale=self.cfg.high_vol_position_scale,
                )
            if regime == REGIME_TREND:
                return self._dynamic(
                    signal, requested, regime, atr_value, atr_pct, adx_value, vol
                )
            return self._fixed(
                signal, requested, regime, atr_value, atr_pct, adx_value, vol
            )
        if requested == "dynamic":
            return self._dynamic(
                signal, requested, regime, atr_value, atr_pct, adx_value, vol
            )
        return self._fixed(
            signal, requested, regime, atr_value, atr_pct, adx_value, vol
        )

    def _fixed(
        self,
        signal: Signal,
        requested: str,
        regime: str,
        atr_value: Decimal | None,
        atr_pct: Decimal | None,
        adx_value: Decimal | None,
        vol: Decimal | None,
    ) -> RateDecision:
        tp = _clamp(_fixed_tp(signal, self.cfg), self.cfg.min_tp_pct, self.cfg.max_tp_pct)
        sl = _clamp(self.cfg.default_sl_pct, self.cfg.min_sl_pct, self.cfg.max_sl_pct)
        risk = _clamp(self.cfg.default_risk_pct, self.cfg.min_risk_pct, self.cfg.max_risk_pct)
        reason = f"fixed:{signal.kind}:{regime}"
        slog(
            "RATE_DECIDED",
            reason,
            mode="fixed",
            take_profit_pct=str(tp),
            stop_loss_pct=str(sl),
            risk_pct=str(risk),
        )
        return RateDecision(
            mode="fixed",
            requested_mode=requested,
            take_profit_pct=tp,
            stop_loss_pct=sl,
            risk_pct=risk,
            reason=reason,
            market_regime=regime,
            atr=atr_value,
            atr_pct=atr_pct,
            adx=adx_value,
            realized_vol_pct=vol,
        )

    def _dynamic(
        self,
        signal: Signal,
        requested: str,
        regime: str,
        atr_value: Decimal | None,
        atr_pct: Decimal | None,
        adx_value: Decimal | None,
        vol: Decimal | None,
        position_scale: Decimal = ONE,
    ) -> RateDecision:
        if atr_value is None or atr_pct is None or atr_value <= ZERO or atr_pct <= ZERO:
            slog("RATE_DECIDED", "abnormal_atr; refusing dynamic rates")
            return RateDecision(
                mode="dynamic",
                requested_mode=requested,
                take_profit_pct=ZERO,
                stop_loss_pct=ZERO,
                risk_pct=ZERO,
                reason="abnormal_atr",
                market_regime=regime,
                position_scale=position_scale,
                atr=atr_value,
                atr_pct=atr_pct,
                adx=adx_value,
                realized_vol_pct=vol,
                ok=False,
            )
        base_tp = _fixed_tp(signal, self.cfg)
        # Low vol → tighter; high vol → wider, still clamped.
        vol_term = vol if vol is not None else atr_pct
        raw_tp = max(base_tp, atr_pct * D("2.2"), vol_term * D("3"))
        raw_sl = max(self.cfg.default_sl_pct, atr_pct * D("1.4"), vol_term * D("2"))
        if regime == REGIME_TREND:
            raw_tp = max(raw_tp, base_tp * D("1.2"))
        tp = _clamp(raw_tp, self.cfg.min_tp_pct, self.cfg.max_tp_pct)
        sl = _clamp(raw_sl, self.cfg.min_sl_pct, self.cfg.max_sl_pct)
        if sl >= tp:
            sl = _clamp(tp * D("0.6"), self.cfg.min_sl_pct, self.cfg.max_sl_pct)
        risk = _clamp(self.cfg.default_risk_pct, self.cfg.min_risk_pct, self.cfg.max_risk_pct)
        if regime == REGIME_HIGH_VOLATILITY:
            risk = _clamp(risk * D("0.5"), self.cfg.min_risk_pct, self.cfg.max_risk_pct)
            position_scale = min(position_scale, self.cfg.high_vol_position_scale)
        reason = f"dynamic:{signal.kind}:{regime}"
        slog(
            "RATE_DECIDED",
            reason,
            mode="dynamic",
            take_profit_pct=str(tp),
            stop_loss_pct=str(sl),
            risk_pct=str(risk),
            position_scale=str(position_scale),
        )
        return RateDecision(
            mode="dynamic",
            requested_mode=requested,
            take_profit_pct=tp,
            stop_loss_pct=sl,
            risk_pct=risk,
            reason=reason,
            market_regime=regime,
            position_scale=position_scale,
            atr=atr_value,
            atr_pct=atr_pct,
            adx=adx_value,
            realized_vol_pct=vol,
        )
