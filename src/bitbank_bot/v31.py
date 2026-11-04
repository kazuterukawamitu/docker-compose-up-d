"""V31 production evaluator (safe plugin).

Wraps the README Granville strategy. Never imports order clients and never
calls ``create_order``. Discovered by ``dual_run`` as the production path.
"""

from __future__ import annotations

from bitbank_bot.config import Config
from bitbank_bot.strategy import MarketSnapshot, Position, Signal
from bitbank_bot.strategy import Strategy as CoreStrategy


class Strategy:  # noqa: A001 — dual_run looks for this name in the plugin module
    """Production evaluator. Same signals as package Strategy."""

    def __init__(self, cfg: Config) -> None:
        self._core = CoreStrategy(cfg)
        self.name = "v31_strategy"

    def observe(self, snap: MarketSnapshot) -> None:
        self._core.observe(snap)

    def evaluate(self, snap: MarketSnapshot, position: Position | None) -> Signal:
        return self._core.evaluate(snap, position)
