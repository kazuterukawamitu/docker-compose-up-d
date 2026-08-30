import pytest

from bitbank_bot.rest_client import RestClient


def test_public_ticker_smoke() -> None:
    client = RestClient(
        public_url="https://public.bitbank.cc",
        private_url="https://api.bitbank.cc/v1",
        timeout_sec=10.0,
        max_retries=2,
    )
    try:
        data = client.get_ticker("btc_jpy")
    except Exception as exc:
        pytest.skip(f"network unavailable: {exc}")
    finally:
        client.close()
    assert data.get("last")
    assert str(data["last"]).replace(".", "", 1).isdigit()
