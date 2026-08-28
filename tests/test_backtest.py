from decimal import Decimal
from pathlib import Path

from tests.conftest import make_settings
from bitbank_bot.backtest import load_candles_csv, run_backtest


def test_backtest_runs_on_fixture(tmp_path: Path) -> None:
    csv_path = Path("tests/fixtures/sample_ohlcv.csv")
    candles = load_candles_csv(csv_path)
    settings = make_settings(tmp_path)
    metrics = run_backtest(candles, settings, starting_jpy=Decimal("1000000"))
    assert metrics["bars"] == float(len(candles))
    assert "profit_factor" in metrics
    assert "max_drawdown" in metrics
    assert "sharpe" in metrics
