"""FIXED / DYNAMIC / AUTO take-profit, stop-loss, and risk percentages.

Strategy still owns BUY/SELL/HOLD. This module only sizes the *rates*
that already exist as per-setup constants (BUY1 +3%, BUY2 +5%/+8%, …).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Sequence

from bitbank_bot.config import Config
from bitbank_bot.indicators import adx, atr, last_finite, realized_vol
from bitbank_bot.logging_setup import slog
from bitbank_bot.market_data import Candle
from bitbank_bot.money import D, ZERO
from bitbank_bot.strategy import Signal


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
    size_multiplier: Decimal = D("1")
    atr: Decimal | None = None
    atr_pct: Decimal | None = None
    adx: Decimal | None = None
    realized_vol: Decimal | None = None
    ok: bool = True

    def as_log(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "take_profit_pct": str(self.take_profit_pct),
            "stop_loss_pct": str(self.stop_loss_pct),
            "risk_pct": str(self.risk_pct),
            "reason": self.reason,
            "market_regime": self.market_regime.value,
            "size_multiplier": str(self.size_multiplier),
            "atr": str(self.atr) if self.atr is not None else None,
            "atr_pct": str(self.atr_pct) if self.atr_pct is not None else None,
            "adx": str(self.adx) if self.adx is not None else None,
            "ok": self.ok,
        }


def parse_rate_mode(raw: str | None) -> RateMode:
    key = (raw or "fixed").strip().lower()
    if key in {"dynamic", "dyn"}:
        return RateMode.DYNAMIC
    if key in {"auto"}:
        return RateMode.AUTO
    return RateMode.FIXED


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def _fixed_tp(signal: Signal, cfg: Config) -> Decimal:
    if signal.tp_pct is not None and signal.tp_pct > ZERO:
        return signal.tp_pct
    kind = (signal.kind or "").upper()
    mapping = {
        "BUY1": cfg.buy1_tp,
        "BUY2": cfg.buy2_golden_tp if signal.golden_cross else cfg.buy2_tp,
        "BUY3": cfg.buy3_tp,
        "BUY4": cfg.buy4_tp,
    }
    return mapping.get(kind, cfg.buy1_tp)


def measure_market(candles: Sequence[Candle], cfg: Config) -> dict[str, Decimal | None]:
    if not candles:
        return {"atr": None, "atr_pct": None, "adx": None, "realized_vol": None}
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    atr_series = atr(highs, lows, closes, cfg.atr_period)
    adx_series = adx(highs, lows, closes, cfg.adx_period)
    atr_val = last_finite(atr_series)
    adx_val = last_finite(adx_series, require_positive=False)
    price = closes[-1]
    atr_pct = (atr_val / price) if atr_val is not None and price > ZERO else None
    vol = realized_vol(closes, cfg.vol_period)
    return {
        "atr": atr_val,
        "atr_pct": atr_pct,
        "adx": adx_val,
        "realized_vol": vol,
    }


def detect_regime(metrics: dict[str, Decimal | None], cfg: Config) -> MarketRegime:
    atr_pct = metrics.get("atr_pct")
    adx_val = metrics.get("adx")
    vol = metrics.get("realized_vol")
    high_vol = False
    if atr_pct is not None and atr_pct >= cfg.high_vol_atr_pct:
        high_vol = True
    if vol is not None and vol >= cfg.high_vol_realized:
        high_vol = True
    if high_vol:
        return MarketRegime.HIGH_VOLATILITY
    if adx_val is not None and adx_val >= cfg.trend_adx:
        return MarketRegime.TREND
    if adx_val is not None and adx_val <= cfg.range_adx:
        return MarketRegime.RANGE
    return MarketRegime.NORMAL


class RateEngine:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.mode = parse_rate_mode(cfg.rate_mode)

    def decide(
        self,
        signal: Signal,
        candles: Sequence[Candle],
        *,
        price: Decimal | None = None,
    ) -> RateDecision:
        metrics = measure_market(candles, self.cfg)
        regime = detect_regime(metrics, self.cfg)
        fixed_tp = _fixed_tp(signal, self.cfg)
        chosen = self.mode
        reason = "fixed_strategy_tp"
        size_mult = D("1")
        if self.mode is RateMode.AUTO:
            if regime is MarketRegime.HIGH_VOLATILITY:
                chosen = RateMode.DYNAMIC
                size_mult = self.cfg.high_vol_size_mult
                reason = "auto_high_vol_dynamic"
            elif regime is MarketRegime.TREND:
                chosen = RateMode.DYNAMIC
                reason = "auto_trend_dynamic"
            elif regime is MarketRegime.RANGE:
                chosen = RateMode.FIXED
                reason = "auto_range_fixed"
                if self.cfg.range_suppress_entries and (signal.side == "buy"):
                    return RateDecision(
                        mode=chosen,
                        take_profit_pct=fixed_tp,
                        stop_loss_pct=self.cfg.default_sl_pct,
                        risk_pct=self.cfg.default_risk_pct,
                        reason="auto_range_suppress_entry",
                        market_regime=regime,
                        size_multiplier=ZERO,
                        atr=metrics["atr"],
                        atr_pct=metrics["atr_pct"],
                        adx=metrics["adx"],
                        realized_vol=metrics["realized_vol"],
                        ok=False,
                    )
            else:
                chosen = RateMode.FIXED
                reason = "auto_normal_fixed"
        if chosen is RateMode.FIXED:
            decision = RateDecision(
                mode=RateMode.FIXED,
                take_profit_pct=fixed_tp,
                stop_loss_pct=self.cfg.default_sl_pct,
                risk_pct=self.cfg.default_risk_pct,
                reason=reason,
                market_regime=regime,
                size_multiplier=size_mult,
                atr=metrics["atr"],
                atr_pct=metrics["atr_pct"],
                adx=metrics["adx"],
                realized_vol=metrics["realized_vol"],
                ok=True,
            )
            slog("RATE_DECIDED", "FIXED rates", **decision.as_log())
            return decision
        atr_pct = metrics["atr_pct"]
        if atr_pct is None or atr_pct <= ZERO:
            slog(
                "RATE_DECIDED",
                "DYNAMIC blocked; ATR missing or non-positive",
                regime=regime.value,
            )
            return RateDecision(
                mode=RateMode.DYNAMIC,
                take_profit_pct=fixed_tp,
                stop_loss_pct=self.cfg.default_sl_pct,
                risk_pct=self.cfg.default_risk_pct,
                reason="abnormal_atr",
                market_regime=regime,
                size_multiplier=ZERO,
                atr=metrics["atr"],
                atr_pct=atr_pct,
                adx=metrics["adx"],
                realized_vol=metrics["realized_vol"],
                ok=False,
            )
        px = price if price is not None else candles[-1].close
        if px <= ZERO:
            return RateDecision(
                mode=RateMode.DYNAMIC,
                take_profit_pct=fixed_tp,
                stop_loss_pct=self.cfg.default_sl_pct,
                risk_pct=self.cfg.default_risk_pct,
                reason="invalid_price",
                market_regime=regime,
                ok=False,
                atr=metrics["atr"],
                atr_pct=atr_pct,
                adx=metrics["adx"],
                realized_vol=metrics["realized_vol"],
            )
        tp = _clamp(atr_pct * self.cfg.dynamic_tp_atr_mult, self.cfg.min_tp_pct, self.cfg.max_tp_pct)
        sl = _clamp(atr_pct * self.cfg.dynamic_sl_atr_mult, self.cfg.min_sl_pct, self.cfg.max_sl_pct)
        if regime is MarketRegime.TREND:
            tp = _clamp(tp * D("1.25"), self.cfg.min_tp_pct, self.cfg.max_tp_pct)
            reason = reason + "+trend_runner" if "+" not in reason else reason
        risk = _clamp(self.cfg.default_risk_pct, self.cfg.min_risk_pct, self.cfg.max_risk_pct)
        if regime is MarketRegime.HIGH_VOLATILITY:
            risk = _clamp(risk * D("0.5"), self.cfg.min_risk_pct, self.cfg.max_risk_pct)
            size_mult = min(size_mult, self.cfg.high_vol_size_mult)
        decision = RateDecision(
            mode=RateMode.DYNAMIC,
            take_profit_pct=tp,
            stop_loss_pct=sl,
            risk_pct=risk,
            reason=reason,
            market_regime=regime,
            size_multiplier=size_mult,
            atr=metrics["atr"],
            atr_pct=atr_pct,
            adx=metrics["adx"],
            realized_vol=metrics["realized_vol"],
            ok=True,
        )
        slog("RATE_DECIDED", "DYNAMIC rates", **decision.as_log())
        return decision
