from __future__ import annotations

from bitbank_bot.rest_client import OrderSubmitUncertain
from bitbank_bot.self_healing import (
    BreakerState,
    CircuitBreaker,
    ErrorClass,
    ErrorClassifier,
    QuarantineManager,
    RetryManager,
    TaskSupervisor,
)


def test_classifier() -> None:
    clf = ErrorClassifier()
    assert clf.classify(TimeoutError("t")) is ErrorClass.TRANSIENT
    assert clf.classify(OrderSubmitUncertain("u")) is ErrorClass.STATE_ERROR
    assert clf.classify(SystemExit()) is ErrorClass.FATAL


def test_retry_get_succeeds_second_try() -> None:
    calls = {"n": 0}

    def flaky() -> int:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("once")
        return 7

    assert RetryManager(max_attempts=3, cap=0.01).call_get(flaky, label="x") == 7
    assert calls["n"] == 2


def test_circuit_opens() -> None:
    br = CircuitBreaker(failures=2, reset_sec=60)
    br.failure()
    br.failure()
    assert br.state is BreakerState.OPEN
    assert br.allow() is False


def test_quarantine_and_supervisor() -> None:
    q = QuarantineManager()
    q.quarantine("trading_loop", "crash")
    assert q.is_quarantined("trading_loop")
    sup = TaskSupervisor(crash_limit=2)
    assert sup.note_crash(RuntimeError("a")) is False
    assert sup.note_crash(RuntimeError("b")) is True
