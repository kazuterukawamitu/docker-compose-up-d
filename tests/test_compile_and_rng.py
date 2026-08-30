from __future__ import annotations

import compileall
from pathlib import Path

from bitbank_bot.rng import SeededRNG, jitter


def test_compileall_src_and_tests() -> None:
    root = Path(__file__).resolve().parents[1]
    assert compileall.compile_dir(str(root / "src"), quiet=1)
    assert compileall.compile_dir(str(root / "tests"), quiet=1)


def test_seeded_rng_is_reproducible() -> None:
    a = SeededRNG(7)
    b = SeededRNG(7)
    assert a.uniform(0, 1) == b.uniform(0, 1)
    assert jitter(1.0, rng=SeededRNG(3)) == jitter(1.0, rng=SeededRNG(3))
