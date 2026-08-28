from bitbank_bot.models import BotStats, Signal
from bitbank_bot.watchdog import WatchInput, diagnose
from tests.conftest import make_settings


def _inp(**kwargs: object) -> WatchInput:
    base: dict[str, object] = dict(
        now_ms=100_000,
        started_ms=0,
        timeout_ms=900_000,
        stale_ms=15_000,
        last_market_data_ms=99_000,
        strategy_evaluations=10,
        buy_signals=0,
        sell_signals=0,
        order_attempts=0,
        last_signal=Signal(action="HOLD", rule_id="none", reason="no setup"),
        last_error="",
        last_block_reason="",
        ws_ok=True,
    )
    base.update(kwargs)
    if "last_market_data_ms" not in kwargs:
        base["last_market_data_ms"] = int(base["now_ms"]) - 1_000  # type: ignore[arg-type]
    return WatchInput(**base)  # type: ignore[arg-type]


def test_normal_wait_before_timeout() -> None:
    status, reason = diagnose(_inp())
    assert status == "NORMAL_WAIT"
    assert "conditions not met" in reason


def test_long_wait_after_timeout_is_not_fail() -> None:
    status, reason = diagnose(_inp(started_ms=0, now_ms=901_000))
    assert status == "LONG_WAIT"
    assert "Market conditions not met" in reason


def test_fail_when_market_never_arrives() -> None:
    status, reason = diagnose(_inp(last_market_data_ms=0, now_ms=901_000, strategy_evaluations=0))
    assert status == "FAIL"
    assert "never received" in reason


def test_fail_when_market_stale_after_timeout() -> None:
    status, reason = diagnose(_inp(last_market_data_ms=1, now_ms=901_000, stale_ms=15_000))
    assert status == "FAIL"
    assert "MARKET_DATA_STALE" in reason


def test_fail_when_strategy_never_runs() -> None:
    status, reason = diagnose(_inp(strategy_evaluations=0, now_ms=901_000))
    assert status == "FAIL"
    assert "strategy has never been executed" in reason


def test_fail_when_signal_never_reaches_order_manager() -> None:
    status, reason = diagnose(
        _inp(
            now_ms=901_000,
            buy_signals=2,
            order_attempts=0,
            last_block_reason="",
            last_signal=Signal(action="BUY", rule_id="buy_1", reason="x"),
        )
    )
    assert status == "FAIL"
    assert "OrderManager" in reason


def test_risk_block_is_long_wait_not_fail() -> None:
    status, reason = diagnose(
        _inp(
            now_ms=901_000,
            buy_signals=1,
            order_attempts=0,
            last_block_reason="kill switch is set",
            last_signal=Signal(action="BUY", rule_id="buy_1", reason="x"),
        )
    )
    assert status == "LONG_WAIT"
    assert "kill switch" in reason


def test_from_stats_round_trip() -> None:
    from bitbank_bot.watchdog import from_stats

    stats = BotStats(started_ms=1, strategy_evaluations=3, last_market_data_ms=50)
    inp = from_stats(stats, now_ms=100, timeout_ms=900_000, stale_ms=15_000, ws_ok=True)
    assert inp.strategy_evaluations == 3
    settings = make_settings()
    assert settings.no_trade_timeout_seconds == 900
