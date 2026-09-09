from __future__ import annotations

from types import SimpleNamespace

from bitbank_bot.watchdog import (
    FAIL,
    LONG_WAIT,
    NORMAL_WAIT,
    SIGNAL,
    RuntimeWatchdog,
    classify,
)


def test_hold_under_timeout_is_normal_wait() -> None:
    report = classify(
        uptime_sec=60,
        timeout_sec=900,
        strategy_evaluations=3,
        market_ok=True,
    )
    assert report.status == NORMAL_WAIT
    assert report.reason == "waiting_for_setup"


def test_hold_over_timeout_is_long_wait_not_fail() -> None:
    report = classify(
        uptime_sec=901,
        timeout_sec=900,
        strategy_evaluations=10,
        market_ok=True,
    )
    assert report.status == LONG_WAIT
    assert report.reason == "market_conditions_not_met"


def test_fail_reason_wins() -> None:
    report = classify(
        uptime_sec=10,
        timeout_sec=900,
        strategy_evaluations=1,
        market_ok=True,
        fail_reason="synthetic_fallback_no_orders",
    )
    assert report.status == FAIL
    assert report.reason == "synthetic_fallback_no_orders"


def test_missing_market_is_fail() -> None:
    report = classify(
        uptime_sec=30,
        timeout_sec=900,
        strategy_evaluations=0,
        market_ok=False,
    )
    assert report.status == FAIL
    assert report.reason == "market_data_stale_or_missing"


def test_strategy_never_ran_after_timeout_is_fail() -> None:
    report = classify(
        uptime_sec=900,
        timeout_sec=900,
        strategy_evaluations=0,
        market_ok=True,
    )
    assert report.status == FAIL
    assert report.reason == "strategy_never_executed"


def test_buy_or_sell_is_signal() -> None:
    report = classify(
        uptime_sec=5,
        timeout_sec=900,
        strategy_evaluations=1,
        market_ok=True,
        has_order_signal=True,
    )
    assert report.status == SIGNAL


def test_runtime_watchdog_ignores_never_marked() -> None:
    health = SimpleNamespace(
        last_loop_at=0.0,
        last_ticker_at=0.0,
        last_candle_at=0.0,
        last_ws_at=0.0,
        last_rest_at=0.0,
        last_strategy_at=0.0,
        last_order_check_at=0.0,
        last_balance_at=0.0,
    )
    dog = RuntimeWatchdog(health, stale_sec=1.0, interval_sec=30.0)
    assert dog.inspect(now=100.0) == []


def test_runtime_watchdog_flags_stale_and_recovers() -> None:
    seen: list[str] = []
    health = SimpleNamespace(
        last_loop_at=1.0,
        last_ticker_at=90.0,
        last_candle_at=90.0,
        last_ws_at=1.0,
        last_rest_at=90.0,
        last_strategy_at=90.0,
        last_order_check_at=90.0,
        last_balance_at=90.0,
    )
    dog = RuntimeWatchdog(
        health, stale_sec=10.0, interval_sec=30.0, on_recover=seen.extend
    )
    findings = dog.inspect(now=100.0)
    assert "loop" in findings
    assert "ws" in findings
    assert "ticker" not in findings
    dog.on_recover(findings)
    assert "ws" in seen
