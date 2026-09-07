from __future__ import annotations

import httpx
import pytest


def _get(url: str) -> httpx.Response:
    try:
        return httpx.get(url, timeout=15)
    except httpx.HTTPError as exc:
        pytest.skip(f"public API not reachable: {type(exc).__name__}")


def test_public_ticker_btc_jpy() -> None:
    response = _get("https://public.bitbank.cc/btc_jpy/ticker")
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("success") == 1
    last = payload["data"]["last"]
    assert last
    float(last)  # numeric string from Bitbank


def test_public_5min_candlestick_jst_today() -> None:
    from datetime import datetime, timedelta, timezone

    jst = timezone(timedelta(hours=9))
    day = datetime.now(jst).strftime("%Y%m%d")
    url = f"https://public.bitbank.cc/btc_jpy/candlestick/5min/{day}"
    response = _get(url)
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("success") == 1
    sticks = payload["data"]["candlestick"]
    assert sticks
    assert sticks[0]["type"] == "5min"
    assert sticks[0]["ohlcv"]
