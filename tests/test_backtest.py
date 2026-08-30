from bitbank_bot.backtest import run_backtest
from bitbank_bot.config import Config
from bitbank_bot.market_data import Candle, track_record_candles
from bitbank_bot.money import D
from bitbank_bot.risk import RiskManager

from helpers import cfg


def _candles(prices: list[str], start_ms: int = 1_700_000_000_000, step_ms: int = 3_600_000) -> list[Candle]:
    out: list[Candle] = []
    for i, raw in enumerate(prices):
        px = D(raw)
        out.append(
            Candle(
                open=px,
                high=px,
                low=px,
                close=px,
                volume=D("1"),
                timestamp_ms=start_ms + i * step_ms,
            )
        )
    return out


def _buy1_then_tp_prices() -> list[str]:
    # SMA(3): downtrend, then MA turns up as price crosses above MA (BUY1),
    # then close clears +3% take-profit.
    return [
        "100000",
        "90000",
        "80000",
        "70000",
        "60000",
        "50000",
        "50000",
        "80000",
        "90000",
    ]


def test_track_record_round_trip_without_kill_switch() -> None:
    c = cfg(
        ma_period=3,
        short_ma_period=3,
        long_ma_period=3,
        kill_switch=False,
        daily_pnl_floor=D("150"),
        max_daily_loss_jpy=D("0"),
        max_position_btc=D("1"),
    )
    report = run_backtest(_candles(_buy1_then_tp_prices()), c, initial_jpy=D("1000000"))
    assert report.trades >= 1
    assert report.wins >= 1
    assert report.last_block_reason != "kill_switch"
    assert all(t.pnl >= D("0") for t in report.closed if t.reason == "TP")
    assert report.closed
    first = report.closed[0]
    assert first.entry_price > D("0")
    assert first.exit_price > first.entry_price or first.reason == "mark_to_market"


def test_same_day_loss_uses_daily_floor_not_kill_switch() -> None:
    c = cfg(
        ma_period=3,
        short_ma_period=3,
        long_ma_period=3,
        kill_switch=False,
        daily_pnl_floor=D("150"),
        max_daily_loss_jpy=D("0"),
        max_position_btc=D("1"),
    )
    risk = RiskManager(c, killed=False)
    risk.set_as_of(1_700_000_000_000)
    risk.record_realized_pnl(D("-400"))
    assert risk.halt_reason() == "daily_pnl_floor"
    blocked = risk.check_buy(D("0"), D("0.1"))
    assert blocked.reason == "daily_pnl_floor"
    assert blocked.reason != "kill_switch"
    # Next JST day (candle + 24h) must accept a new buy.
    risk.set_as_of(1_700_000_000_000 + 24 * 60 * 60 * 1000)
    allowed = risk.check_buy(D("0"), D("0.1"))
    assert allowed.allowed
    assert allowed.reason == "ok"


def test_default_policy_track_record_is_a_winning_round_trip() -> None:
    c = Config(kill_switch=False, kill_switch_path="/tmp/bitbank-bot-tests-no-kill-file")
    report = run_backtest(track_record_candles(), c, initial_jpy=D("1000000"))
    assert report.trades >= 1
    assert report.wins >= 1
    assert report.blocked_buys == 0
    assert report.last_block_reason != "kill_switch"
    assert any(t.kind == "BUY1" and t.reason == "TP" and t.pnl > D("0") for t in report.closed)


def test_backtest_reports_track_record_fields() -> None:
    c = cfg(ma_period=3, short_ma_period=3, long_ma_period=3, kill_switch=False)
    report = run_backtest(_candles(_buy1_then_tp_prices()), c, initial_jpy=D("1000000"))
    payload = report.as_dict()
    assert "closed" in payload
    assert payload["trades"] >= 1
    assert payload["last_block_reason"] != "kill_switch"
