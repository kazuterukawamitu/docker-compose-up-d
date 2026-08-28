import pytest

from bitbank_bot.config import load_settings
from bitbank_bot.exchange.bitbank_rest import BitbankRest


@pytest.mark.network
@pytest.mark.asyncio
async def test_public_ticker_btc_jpy() -> None:
    settings = load_settings(None)
    async with BitbankRest(settings) as rest:
        ticker = await rest.fetch_ticker("btc_jpy")
    assert ticker.last > 0
    assert ticker.buy > 0
    assert ticker.sell > 0
    assert ticker.timestamp_ms > 0
