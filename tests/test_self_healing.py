from __future__ import annotations

from bitbank_bot.rest_client import BitbankAPIError
from bitbank_bot.self_healing import ErrorClass, HealAction, classify_error, retry_get


def test_timeout_is_transient() -> None:
    assert classify_error(TimeoutError("x")) is ErrorClass.TRANSIENT


def test_auth_is_fatal() -> None:
    assert classify_error(BitbankAPIError("no", code=20001, http_status=401)) is ErrorClass.FATAL


def test_retry_get_eventually_works() -> None:
    state = {"n": 0}

    def fn() -> str:
        state["n"] += 1
        if state["n"] < 2:
            raise TimeoutError("once")
        return "ok"

    assert retry_get(fn, attempts=3, label="t") == "ok"


def test_retry_get_refuses_side_effect() -> None:
    try:
        retry_get(lambda: 1, side_effect=True)
        raised = False
    except RuntimeError:
        raised = True
    assert raised
    assert HealAction.STOP.value == "STOP"
