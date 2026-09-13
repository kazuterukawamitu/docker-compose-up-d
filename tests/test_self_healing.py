from __future__ import annotations

from bitbank_bot.self_healing import CircuitBreaker, ErrorClass, classify_error


def test_classify_timeout_transient() -> None:
    assert classify_error(TimeoutError("x")) == ErrorClass.TRANSIENT


def test_classify_auth_fatal() -> None:
    assert classify_error(reason="auth_failure") == ErrorClass.FATAL


def test_circuit_opens() -> None:
    br = CircuitBreaker(threshold=2, cooldown_sec=60)
    br.failure()
    assert br.allow()
    br.failure()
    assert br.state.value == "OPEN"
    assert br.allow() is False
    br.success()
    assert br.allow()
