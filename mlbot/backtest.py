"""A simple long-only backtest engine for :class:`MovingAverageStrategy`."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .strategy import MovingAverageStrategy, StrategyParams


@dataclass
class Trade:
    entry_time: object
    entry_price: float
    exit_time: object
    exit_price: float
    reason: str

    @property
    def return_pct(self) -> float:
        return self.exit_price / self.entry_price - 1.0


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trades: list[Trade] = field(default_factory=list)
    initial_cash: float = 0.0

    @property
    def final_equity(self) -> float:
        return float(self.equity_curve.iloc[-1])

    @property
    def total_return_pct(self) -> float:
        return self.final_equity / self.initial_cash - 1.0

    @property
    def num_trades(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.return_pct > 0)
        return wins / len(self.trades)

    @property
    def max_drawdown_pct(self) -> float:
        curve = self.equity_curve
        running_max = curve.cummax()
        drawdown = curve / running_max - 1.0
        return float(drawdown.min())

    def summary(self) -> str:
        lines = [
            "Backtest results",
            "================",
            f"Initial cash    : {self.initial_cash:,.2f}",
            f"Final equity    : {self.final_equity:,.2f}",
            f"Total return    : {self.total_return_pct * 100:,.2f}%",
            f"Number of trades: {self.num_trades}",
            f"Win rate        : {self.win_rate * 100:,.1f}%",
            f"Max drawdown    : {self.max_drawdown_pct * 100:,.2f}%",
        ]
        return "\n".join(lines)


class Backtester:
    """Run the moving-average strategy over a price series.

    The engine is long-only and all-in: an entry deploys all available cash, and
    an exit liquidates the whole position. A ``fee`` (fraction) is charged on both
    sides of every trade.
    """

    def __init__(
        self,
        strategy: MovingAverageStrategy | None = None,
        initial_cash: float = 10_000.0,
        fee: float = 0.0005,
    ) -> None:
        self.strategy = strategy or MovingAverageStrategy(StrategyParams())
        self.initial_cash = initial_cash
        self.fee = fee

    def run(self, df: pd.DataFrame) -> BacktestResult:
        signals = self.strategy.generate_signals(df)

        cash = self.initial_cash
        units = 0.0
        entry_price = 0.0
        entry_time = None
        take_profit_price = 0.0

        equity = np.empty(len(signals))
        trades: list[Trade] = []

        closes = signals["close"].to_numpy()
        sma = signals["sma"].to_numpy()
        cross_up = signals["cross_up"].to_numpy()
        cross_down = signals["cross_down"].to_numpy()
        tp_pct = signals["take_profit_pct"].to_numpy()
        index = signals.index

        for i in range(len(signals)):
            price = closes[i]

            if units > 0.0:
                hit_take_profit = price >= take_profit_price
                crossed_down = bool(cross_down[i])
                if hit_take_profit or crossed_down:
                    cash = units * price * (1.0 - self.fee)
                    trades.append(
                        Trade(
                            entry_time=entry_time,
                            entry_price=entry_price,
                            exit_time=index[i],
                            exit_price=price,
                            reason="take_profit" if hit_take_profit else "cross_down",
                        )
                    )
                    units = 0.0

            if units == 0.0 and bool(cross_up[i]) and not np.isnan(sma[i]):
                target = tp_pct[i]
                if not np.isnan(target):
                    units = (cash * (1.0 - self.fee)) / price
                    entry_price = price
                    entry_time = index[i]
                    take_profit_price = price * (1.0 + target)
                    cash = 0.0

            equity[i] = cash + units * price

        equity_curve = pd.Series(equity, index=index, name="equity")
        return BacktestResult(
            equity_curve=equity_curve,
            trades=trades,
            initial_cash=self.initial_cash,
        )
