"""Deterministic unit tests for the moving-average backtester.

Run with: ``python -m unittest discover -s tests``
"""

import unittest

import numpy as np
import pandas as pd

from mlbot import (
    Backtester,
    MovingAverageStrategy,
    StrategyParams,
    generate_price_series,
)


class SignalTests(unittest.TestCase):
    def test_cross_up_and_down_detected(self):
        # V-shaped price that dips below then rises above a short SMA.
        prices = [10, 10, 10, 9, 8, 7, 8, 9, 11, 13, 15]
        df = pd.DataFrame({"close": prices})
        strat = MovingAverageStrategy(StrategyParams(window=3))
        sig = strat.generate_signals(df)

        self.assertTrue(sig["cross_up"].any(), "expected at least one upward cross")
        self.assertTrue(sig["cross_down"].any(), "expected at least one downward cross")

    def test_take_profit_only_on_entry_bars(self):
        df = generate_price_series(periods=300, seed=3)
        strat = MovingAverageStrategy(StrategyParams(window=20))
        sig = strat.generate_signals(df)
        # take_profit_pct is defined exactly on the cross_up bars.
        tp_defined = sig["take_profit_pct"].notna()
        pd.testing.assert_series_equal(
            tp_defined, sig["cross_up"], check_names=False
        )


class BacktestTests(unittest.TestCase):
    def test_take_profit_exit(self):
        # Rise above SMA, then jump so the +5% target is clearly hit.
        prices = [100, 100, 100, 100, 101, 103, 120, 121, 122]
        df = pd.DataFrame({"close": prices})
        strat = MovingAverageStrategy(
            StrategyParams(
                window=3,
                take_profit_uptrend=0.05,
                take_profit_default=0.05,
                take_profit_flat=0.05,
            )
        )
        result = Backtester(strat, initial_cash=1000.0, fee=0.0).run(df)

        self.assertGreaterEqual(result.num_trades, 1)
        self.assertTrue(
            any(t.reason == "take_profit" for t in result.trades),
            "expected a take-profit exit",
        )
        winning = [t for t in result.trades if t.reason == "take_profit"]
        self.assertGreaterEqual(winning[0].return_pct, 0.05 - 1e-9)

    def test_equity_curve_length_and_conservation(self):
        df = generate_price_series(periods=400, seed=5)
        result = Backtester(initial_cash=10_000.0, fee=0.0).run(df)
        self.assertEqual(len(result.equity_curve), len(df))
        # With zero fees and no open position at the start, equity starts at cash.
        self.assertAlmostEqual(result.equity_curve.iloc[0], 10_000.0, places=6)
        self.assertFalse(np.isnan(result.final_equity))


if __name__ == "__main__":
    unittest.main()
