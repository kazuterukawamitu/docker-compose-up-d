"""KY / 危険予知: present-data hazard probability. No look-ahead, never 100% future."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from bitbank_bot.config import Config
from bitbank_bot.indicators import Trend
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO
from bitbank_bot.strategy import MarketSnapshot


# Never claim certainty about the future.
_MAX_PROBABILITY = D("0.99")
_MAX_CONFIDENCE = D("0.95")


@dataclass(frozen=True)
class HazardAssessment:
    probability: Decimal
    confidence: Decimal
    veto: bool
    reasons: tuple[str, ...]

    def as_log(self) -> dict[str, object]:
        return {
            "probability": str(self.probability),
            "confidence": str(self.confidence),
            "veto": self.veto,
            "reasons": list(self.reasons),
            "look_ahead": False,
        }


def anticipate_hazard(
    snap: MarketSnapshot,
    *,
    cfg: Config,
    entropy: Decimal,
    daily_pnl: Decimal,
    htf_down: bool,
    returns: Sequence[Decimal],
    extend_pct: Decimal | None = None,
) -> HazardAssessment:
    """Score hazard from the current bar and already-known returns only."""
    reasons: list[str] = []
    mass = ZERO
    extend = D(extend_pct if extend_pct is not None else cfg.buy3_extend)
    if snap.ma > ZERO:
        distance = (snap.close - snap.ma) / snap.ma
        if distance >= extend:
            mass += D("0.25")
            reasons.append("extended_above_ma")
        elif distance <= -extend:
            mass += D("0.20")
            reasons.append("extended_below_ma")
    if snap.dead_cross:
        mass += D("0.20")
        reasons.append("dead_cross")
    if snap.close < snap.prev_close and snap.ma_trend == Trend.DOWN:
        mass += D("0.15")
        reasons.append("falling_in_downtrend")
    if entropy >= cfg.entropy_high:
        mass += D("0.15")
        reasons.append("high_entropy_uncertain")
    if daily_pnl < ZERO:
        mass += D("0.15")
        reasons.append("intraday_drawdown")
    if htf_down:
        mass += D("0.25")
        reasons.append("htf_downtrend")

    probability = min(mass, _MAX_PROBABILITY)
    known = len(returns)
    window = max(int(cfg.entropy_window), 1)
    confidence = min(D(known) / D(window), _MAX_CONFIDENCE)
    if known < 2:
        confidence = min(confidence, D("0.20"))
        reasons.append("low_sample_confidence")

    veto_prob = D(cfg.ky_veto_probability)
    min_conf = D(cfg.ky_min_confidence)
    veto = False
    if veto_prob > ZERO:
        veto = probability >= veto_prob and confidence >= min_conf
        if veto:
            reasons.append("ky_veto")
    return HazardAssessment(
        probability=probability,
        confidence=confidence,
        veto=veto,
        reasons=tuple(reasons),
    )


def log_hazard(assessment: HazardAssessment) -> None:
    slog("KY", "hazard", **assessment.as_log())
