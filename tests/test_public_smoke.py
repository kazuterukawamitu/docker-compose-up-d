from __future__ import annotations

import httpx


def test_public_ticker_btc_jpy() -> None:
    response = httpx.get("https://public.bitbank.cc/btc_jpy/ticker", timeout=15)
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("success") == 1
    last = payload["data"]["last"]
    assert last
    float(last)  # numeric string from Bitbank
