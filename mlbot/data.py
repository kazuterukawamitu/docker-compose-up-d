"""Price data helpers for the backtester.

Two sources are supported:

* :func:`generate_price_series` produces a deterministic, BTC-like synthetic
  price series so the demo runs anywhere without network access.
* :func:`load_price_series` reads OHLC/close data from a CSV file when the user
  wants to backtest against real market data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate_price_series(
    periods: int = 2000,
    start_price: float = 20000.0,
    freq: str = "h",
    seed: int = 42,
    annual_drift: float = 0.4,
    annual_vol: float = 0.8,
) -> pd.DataFrame:
    """Generate a deterministic, BTC-like price series via geometric Brownian motion.

    Returns a :class:`~pandas.DataFrame` indexed by timestamp with a ``close``
    column. The ``seed`` keeps the output reproducible for demonstrations.
    """
    if periods <= 0:
        raise ValueError("periods must be positive")

    rng = np.random.default_rng(seed)

    periods_per_year = {
        "h": 24 * 365,
        "d": 365,
        "min": 60 * 24 * 365,
    }.get(freq, 24 * 365)

    dt = 1.0 / periods_per_year
    mu = annual_drift
    sigma = annual_vol

    shocks = rng.standard_normal(periods)
    log_returns = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * shocks
    prices = start_price * np.exp(np.cumsum(log_returns))

    index = pd.date_range("2021-01-01", periods=periods, freq=freq)
    return pd.DataFrame({"close": prices}, index=index)


def load_price_series(path: str, column: str = "close") -> pd.DataFrame:
    """Load a price series from a CSV file.

    The CSV must contain a price column (default ``close``). If a ``timestamp``
    or ``time`` column exists it is used as the index; otherwise a plain integer
    index is used.
    """
    df = pd.read_csv(path)

    lowered = {c.lower(): c for c in df.columns}
    if column not in df.columns and column in lowered:
        column = lowered[column]
    if column not in df.columns:
        raise ValueError(
            f"column {column!r} not found in {path}; available: {list(df.columns)}"
        )

    for ts_name in ("timestamp", "time", "date", "datetime"):
        if ts_name in lowered:
            ts_col = lowered[ts_name]
            df[ts_col] = pd.to_datetime(df[ts_col])
            df = df.set_index(ts_col)
            break

    return df[[column]].rename(columns={column: "close"})
