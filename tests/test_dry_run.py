from decimal import Decimal

import pytest

from bitbank_bot.exceptions import ExchangeError
from bitbank_bot.exchange.rest import BitbankRest
from bitbank_bot.models import OrderType, Side


@pytest.mark.asyncio
async def test_rest_create_order_blocked_in_dry_run(settings) -> None:
    rest = BitbankRest(settings)
    with pytest.raises(ExchangeError, match="DRY_RUN"):
        await rest.create_order(
            side=Side.BUY,
            amount=Decimal("0.01"),
            order_type=OrderType.LIMIT,
            price=Decimal("10000000"),
        )
