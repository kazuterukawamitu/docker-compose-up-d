from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from bitbank_bot.models import OrderStatus, Side, Ticker
from bitbank_bot.orders.manager import OrderManager
from bitbank_bot.orders.repository import JsonRepository


def _ticker() -> Ticker:
    px = Decimal("10000000")
    return Ticker(
        pair="btc_jpy",
        last=px,
        bid=px,
        ask=px,
        high=px,
        low=px,
        volume=Decimal("1"),
        timestamp_ms=1,
    )


@pytest.mark.asyncio
async def test_dry_run_never_calls_create_order(settings) -> None:
    rest = AsyncMock()
    rest.create_order = AsyncMock(side_effect=AssertionError("live order must not be sent"))
    repo = JsonRepository(settings.data_dir)
    manager = OrderManager(settings, rest, repo)
    record = await manager.submit(
        side=Side.BUY,
        amount_btc=Decimal("0.01"),
        ticker=_ticker(),
        jpy_free=Decimal("1000000"),
        btc_free=Decimal("0"),
        reason="test dry-run",
        take_profit_pct=Decimal("0.03"),
    )
    rest.create_order.assert_not_called()
    assert record.status is OrderStatus.FILLED
    assert record.dry_run is True
    assert manager.position.is_open
    saved = JsonRepository(settings.data_dir).load_orders()
    assert saved[-1].status is OrderStatus.FILLED


@pytest.mark.asyncio
async def test_json_roundtrip_position(settings) -> None:
    rest = AsyncMock()
    manager = OrderManager(settings, rest, JsonRepository(settings.data_dir))
    await manager.submit(
        side=Side.BUY,
        amount_btc=Decimal("0.01"),
        ticker=_ticker(),
        jpy_free=Decimal("1000000"),
        btc_free=Decimal("0"),
        reason="buy",
        take_profit_pct=Decimal("0.03"),
    )
    reloaded = JsonRepository(settings.data_dir).load_position(settings.pair)
    assert reloaded.amount_btc > 0
    assert reloaded.take_profit_pct == Decimal("0.03")
