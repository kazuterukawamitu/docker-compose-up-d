from __future__ import annotations

from typing import Any

from bitbank_bot.amounts import AmountPlan
from bitbank_bot.money import D
from bitbank_bot.orders import OrderExecutor
from bitbank_bot.strategy import Signal

from helpers import cfg


class FakeClient:
    def __init__(self, active: list[dict[str, Any]] | None = None) -> None:
        self.active = active or []
        self.create_calls: list[dict[str, Any]] = []

    def get_active_orders(self, pair: str) -> list[dict[str, Any]]:
        return list(self.active)

    def create_order(
        self,
        pair: str,
        amount: str,
        side: str,
        order_type: str,
        price: str | None = None,
        post_only: bool | None = None,
    ) -> dict[str, Any]:
        self.create_calls.append(
            {
                "pair": pair,
                "amount": amount,
                "side": side,
                "type": order_type,
                "price": price,
            }
        )
        return {
            "order_id": 1,
            "status": "UNFILLED",
            "executed_amount": "0",
            "average_price": "0",
        }


def _plan(side: str = "buy") -> AmountPlan:
    return AmountPlan(
        side=side,
        amount=D("0.01"),
        price=D("10000000"),
        available_jpy=D("1000000"),
        available_btc=D("0.01"),
        target_jpy=D("100000"),
        planned_order_jpy=D("100000"),
        actual_execution_jpy=None,
        actual_balance_jpy=D("1000000"),
        actual_balance_btc=D("0.01"),
        ok=True,
        reason="ok",
    )


def test_dry_run_never_calls_create_order() -> None:
    client = FakeClient()
    executor = OrderExecutor(cfg(dry_run=True, live_trading=False), client)
    signal = Signal("BUY1", "buy", D("0.03"), "test")
    result = executor.place(signal, _plan())
    assert client.create_calls == []
    assert result.dry_run
    assert result.ok


def test_duplicate_active_order_blocks() -> None:
    client = FakeClient(active=[{"order_id": 9, "pair": "btc_jpy"}])
    executor = OrderExecutor(cfg(dry_run=True, live_trading=False), client)
    result = executor.place(Signal("BUY1", "buy", D("0.03"), "test"), _plan())
    assert result.reason == "active_order_exists"
    assert client.create_calls == []


def test_live_path_would_call_create_order() -> None:
    client = FakeClient()
    executor = OrderExecutor(cfg(dry_run=False, live_trading=True), client)
    result = executor.place(Signal("BUY1", "buy", D("0.03"), "test"), _plan())
    assert len(client.create_calls) == 1
    assert result.executed_amount == D("0")
    assert result.reason == "accepted_unfilled"
