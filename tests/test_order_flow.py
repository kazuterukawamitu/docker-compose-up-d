from decimal import Decimal

import pytest

from bitbank_bot.orders.manager import OrderManager
from bitbank_bot.orders.sizing import SizePlan
from bitbank_bot.orders.states import apply_fill
from bitbank_bot.models import Position
from tests.conftest import make_settings


@pytest.mark.asyncio
async def test_dry_run_simulates_fill_without_client() -> None:
    settings = make_settings()
    manager = OrderManager(settings, client=None)
    plan = SizePlan(target=Decimal("0.0001"), planned=Decimal("0.0001"), price=Decimal("10000000"))
    record = await manager.submit("buy", plan, "test", Decimal("10000000"))
    assert record.status == "DRY_FILLED"
    assert record.executed_amount == Decimal("0.0001")
    assert record.dry_run is True


@pytest.mark.asyncio
async def test_duplicate_in_flight_is_blocked() -> None:
    settings = make_settings()
    manager = OrderManager(settings, client=None)
    manager.in_flight = True
    plan = SizePlan(target=Decimal("0.0001"), planned=Decimal("0.0001"), price=Decimal("1"))
    record = await manager.submit("buy", plan, "test", Decimal("1"))
    assert record.status == "BLOCKED"
    assert "in-flight" in record.reason


@pytest.mark.asyncio
async def test_live_client_fill_uses_executed_amount() -> None:
    settings = make_settings(dry_run=False, api_key="k", api_secret="s")

    class Fake:
        async def create_order(self, pair, side, order_type, amount, price):
            return {
                "order_id": 42,
                "side": side,
                "type": order_type,
                "executed_amount": "0.0001",
                "remaining_amount": "0",
                "average_price": "123",
                "status": "FULLY_FILLED",
            }

        async def get_order(self, pair, order_id):
            raise AssertionError("should not poll when already filled")

        async def active_orders(self, pair):
            return []

    manager = OrderManager(settings, Fake())
    plan = SizePlan(target=Decimal("0.0001"), planned=Decimal("0.0001"), price=Decimal("123"))
    record = await manager.submit("buy", plan, "rule", Decimal("123"))
    assert record.order_id == 42
    assert record.executed_amount == Decimal("0.0001")
    assert record.status == "FULLY_FILLED"


def test_apply_fill_tracks_pnl() -> None:
    pos = Position()
    apply_fill(pos, "buy", Decimal("0.001"), Decimal("100"), 1, Decimal("0.03"), "buy_1")
    pnl = apply_fill(pos, "sell", Decimal("0.001"), Decimal("110"), 2, None, "tp")
    assert pnl == Decimal("0.01")
    assert not pos.is_open
