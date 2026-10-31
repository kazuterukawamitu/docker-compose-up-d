"""OOS / shadow evaluator (safe plugin).

Runs beside production. Never receives an order client and never calls
``create_order``. Tuning proposals are logged only; they are not applied.
"""

from __future__ import annotations

from bitbank_bot.config import Config
from bitbank_bot.strategy import MarketSnapshot, Position, Signal
from bitbank_bot.strategy import Strategy as CoreStrategy


class Strategy:  # noqa: A001 — dual_run looks for this name in the plugin module
    """Shadow evaluator. Mirrors production; execute=false always."""

    def __init__(self, cfg: Config) -> None:
        self._core = CoreStrategy(cfg)
        self.name = "oos_shadow"

    def observe(self, snap: MarketSnapshot) -> None:
        self._core.observe(snap)

    def evaluate(self, snap: MarketSnapshot, position: Position | None) -> Signal:
        signal = self._core.evaluate(snap, position)
        # Tag reason so logs show OOS origin without changing kind/side.
        if signal.reason and not signal.reason.startswith("oos:"):
            return Signal(
                kind=signal.kind,
                side=signal.side,
                tp_pct=signal.tp_pct,
                reason=f"oos:{signal.reason}",
                golden_cross=signal.golden_cross,
                cross_price=signal.cross_price,
                peak_price=signal.peak_price,
                origin_price=signal.origin_price,
                crossover_price_bp=signal.crossover_price_bp,
            )
        return signal
