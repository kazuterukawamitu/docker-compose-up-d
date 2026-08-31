"""Optional seeded RNG for backoff jitter. Never used for live order sizes."""

from __future__ import annotations

import random


class SeededRNG:
    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.seed = seed

    def uniform(self, a: float, b: float) -> float:
        return self._rng.uniform(a, b)

    def jitter_delay(self, delay: float, low: float = 0.5, high: float = 1.5) -> float:
        return delay * self._rng.uniform(low, high)


def jitter(delay: float, *, rng: SeededRNG | random.Random | None = None) -> float:
    source = rng if rng is not None else random
    return delay * source.uniform(0.85, 1.15)
