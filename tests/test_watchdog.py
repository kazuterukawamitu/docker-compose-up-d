from bitbank_bot.watchdog import WatchInput, diagnose


def _inp(**kwargs: object) -> WatchInput:
    base: dict[str, object] = dict(
        now_ms=1_000_000,
        started_ms=1_000_000,
        timeout_ms=900_000,
        stale_ms=60_000,
        last_market_data_ms=999_000,
        strategy_evaluations=3,
        buy_signals=0,
        sell_signals=0,
        order_attempts=0,
        last_signal_kind="HOLD",
        last_signal_reason="no_buy_setup",
        last_error="",
        last_block_reason="",
        ws_ok=True,
    )
    base.update(kwargs)
    return WatchInput(**base)  # type: ignore[arg-type]


def test_normal_wait_before_timeout() -> None:
    status, reason = diagnose(_inp())
    assert status == "NORMAL_WAIT"
    assert "no_buy_setup" in reason


def test_long_wait_after_timeout() -> None:
    status, _reason = diagnose(
        _inp(now_ms=2_000_000, started_ms=1_000_000, last_market_data_ms=1_999_000)
    )
    assert status == "LONG_WAIT"


def test_fail_when_market_never_arrives() -> None:
    status, reason = diagnose(
        _inp(
            last_market_data_ms=0,
            now_ms=2_000_000,
            started_ms=1_000_000,
            strategy_evaluations=0,
        )
    )
    assert status == "FAIL"
    assert "never received" in reason


def test_fail_when_signal_never_reaches_orders() -> None:
    status, reason = diagnose(
        _inp(
            now_ms=2_000_000,
            started_ms=1_000_000,
            last_market_data_ms=1_999_000,
            buy_signals=2,
            order_attempts=0,
            last_block_reason="",
        )
    )
    assert status == "FAIL"
    assert "OrderManager" in reason


def test_blocked_signal_is_long_wait_not_fail() -> None:
    status, reason = diagnose(
        _inp(
            now_ms=2_000_000,
            started_ms=1_000_000,
            last_market_data_ms=1_999_000,
            buy_signals=1,
            order_attempts=0,
            last_block_reason="kill_switch",
        )
    )
    assert status == "LONG_WAIT"
    assert "kill_switch" in reason
