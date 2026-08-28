import csv
from decimal import Decimal
from pathlib import Path

from bitbank_bot.backtest import ascii_chart, load_csv, run_backtest
from bitbank_bot.market.candles import synthetic_trend
from tests.conftest import make_settings


def test_backtest_runs_on_synthetic_csv(tmp_path: Path) -> None:
    candles = synthetic_trend(Decimal("10000000"), [Decimal("-10000")] * 40 + [Decimal("50000")] * 10 + [Decimal("-20000")] * 10)
    csv_path = tmp_path / "candles.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["ts", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for c in candles:
            writer.writerow(
                {
                    "ts": c.ts,
                    "open": str(c.open),
                    "high": str(c.high),
                    "low": str(c.low),
                    "close": str(c.close),
                    "volume": str(c.volume),
                }
            )
    loaded = load_csv(csv_path)
    result = run_backtest(make_settings(tmp_path=tmp_path), loaded)
    assert result.trades >= 0
    chart = ascii_chart(result.equity or [Decimal("1")])
    assert "equity" in chart
