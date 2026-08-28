"""Strategy interface. Sell signals from an earlier plugin win over later buys."""

from __future__ import annotations

from abc import ABC, abstractmethod

from bitbank_bot.models import Signal, Snapshot


class StrategyBase(ABC):
    name: str = "base"

    @abstractmethod
    def evaluate(self, snapshot: Snapshot) -> Signal:
        raise NotImplementedError


class CombinedStrategy(StrategyBase):
    name = "combined"

    def __init__(self, strategies: list[StrategyBase]) -> None:
        self._strategies = strategies

    def evaluate(self, snapshot: Snapshot) -> Signal:
        buy: Signal | None = None
        for strategy in self._strategies:
            signal = strategy.evaluate(snapshot)
            if signal.side is None:
                continue
            if signal.side.value == "sell":
                return signal
            if buy is None:
                buy = signal
        return buy or Signal.hold()
