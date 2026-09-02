from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

from bitbank_bot.amounts import AmountPlan
from bitbank_bot.orders import OrderExecutor
from bitbank_bot.strategy import Signal
from tests.helpers import cfg


def _plan() -> AmountPlan:
    return AmountPlan(
        side="buy",
        amount=Decimal("0.001"),
        price=Decimal("10000000"),
        available_jpy=Decimal("100000"),
        available_btc=Decimal("0"),
        target_jpy=Decimal("94857.5"),
        planned_order_jpy=Decimal("10000"),
        actual_execution_jpy=None,
        actual_balance_jpy=Decimal("100000"),
        actual_balance_btc=Decimal("0"),
        ok=True,
        reason="ok",
    )


def test_dry_run_never_calls_create_order() -> None:
    client = MagicMock()
    client.create_order.side_effect = AssertionError("live order")
    client.get_active_orders.return_value = []
    c = cfg(dry_run=True, live_trading=False)
    result = OrderExecutor(c, client).place(
        Signal("BUY1", "buy", Decimal("0.03"), "test"), _plan()
    )
    assert result.ok
    assert result.dry_run
    assert result.simulated
    assert result.reason == "simulated"
    client.create_order.assert_not_called()


def test_dry_run_intent_only_when_simulate_off() -> None:
    client = MagicMock()
    c = cfg(dry_run=True, live_trading=False, simulate_fill=False)
    result = OrderExecutor(c, client).place(
        Signal("BUY1", "buy", Decimal("0.03"), "test"), _plan()
    )
    assert result.reason == "intent_only"
    assert result.executed_amount == Decimal("0")
    client.create_order.assert_not_called()


def test_bad_plan_does_not_order() -> None:
    client = MagicMock()
    plan = _plan()
    plan.ok = False
    plan.reason = "below_min_amount"
    plan.amount = Decimal("0")
    c = cfg()
    result = OrderExecutor(c, client).place(Signal.hold("x"), plan)
    assert not result.ok
    client.create_order.assert_not_called()


def test_live_path_requires_dual_flag_and_confirms() -> None:
    client = MagicMock()
    client.get_active_orders.return_value = []
    client.create_order.return_value = {
        "order_id": "1",
        "status": "FULLY_FILLED",
        "executed_amount": "0.001",
        "average_price": "10000000",
        "start_amount": "0.001",
    }
    c = cfg(dry_run=False, live_trading=True, api_key="k", api_secret="s")
    assert c.may_place_live_orders
    result = OrderExecutor(c, client).place(
        Signal("BUY1", "buy", Decimal("0.03"), "test"), _plan()
    )
    assert result.ok
    assert not result.dry_run
    client.create_order.assert_called_once()
    kwargs = client.create_order.call_args.kwargs
    assert kwargs["live_confirmed"] is True
    assert kwargs["pair"] == "btc_jpy"


def test_live_unfilled_refreshes_order() -> None:
    client = MagicMock()
    client.get_active_orders.return_value = []
    client.create_order.return_value = {
        "order_id": "42",
        "status": "UNFILLED",
        "executed_amount": "0",
        "average_price": "0",
        "start_amount": "0.001",
    }
    client.get_order.return_value = {
        "order_id": "42",
        "status": "FULLY_FILLED",
        "executed_amount": "0.001",
        "average_price": "10000000",
        "start_amount": "0.001",
    }
    c = cfg(dry_run=False, live_trading=True, api_key="k", api_secret="s")
    result = OrderExecutor(c, client).place(
        Signal("BUY1", "buy", Decimal("0.03"), "test"), _plan()
    )
    assert result.ok
    assert result.status == "FULLY_FILLED"
    assert result.executed_amount == Decimal("0.001")
    client.get_order.assert_called_once()


def test_active_orders_block_live() -> None:
    client = MagicMock()
    client.get_active_orders.return_value = [{"order_id": "9"}]
    c = cfg(dry_run=False, live_trading=True, api_key="k", api_secret="s")
    result = OrderExecutor(c, client).place(
        Signal("BUY1", "buy", Decimal("0.03"), "test"), _plan()
    )
    assert not result.ok
    assert result.reason == "active_orders"
    client.create_order.assert_not_called()


def test_place_rejects_non_finite_amount() -> None:
    client = MagicMock()
    plan = _plan()
    plan.amount = Decimal("NaN")
    c = cfg(dry_run=False, live_trading=True, api_key="k", api_secret="s")
    result = OrderExecutor(c, client).place(
        Signal("BUY1", "buy", Decimal("0.03"), "test"), plan
    )
    assert not result.ok
    assert result.reason == "number_expected"
    client.create_order.assert_not_called()


def test_poll_fill() -> None:
    client = MagicMock()
    client.get_order.return_value = {
        "order_id": "42",
        "status": "FULLY_FILLED",
        "executed_amount": "0.001",
        "average_price": "10000000",
        "start_amount": "0.001",
    }
    c = cfg(dry_run=False, live_trading=True, api_key="k", api_secret="s")
    result = OrderExecutor(c, client).poll("42", Decimal("0.001"))
    assert result.ok
    assert result.reason == "fill"
    assert result.executed_amount == Decimal("0.001")
    assert result.actual_execution_jpy == Decimal("10000")


def test_poll_unfilled() -> None:
    client = MagicMock()
    client.get_order.return_value = {
        "order_id": "42",
        "status": "UNFILLED",
        "executed_amount": "0",
        "average_price": "0",
        "start_amount": "0.001",
    }
    c = cfg(dry_run=False, live_trading=True, api_key="k", api_secret="s")
    result = OrderExecutor(c, client).poll("42", Decimal("0.001"))
    assert result.ok
    assert result.reason == "accepted_unfilled"
    assert result.executed_amount == Decimal("0")


def test_poll_partial_stays_open() -> None:
    client = MagicMock()
    client.get_order.return_value = {
        "order_id": "42",
        "status": "PARTIALLY_FILLED",
        "executed_amount": "0.0004",
        "average_price": "10000000",
        "start_amount": "0.001",
    }
    c = cfg(dry_run=False, live_trading=True, api_key="k", api_secret="s")
    result = OrderExecutor(c, client).poll("42", Decimal("0.001"))
    assert result.ok
    assert result.reason == "partial_fill"
    assert result.executed_amount == Decimal("0.0004")
    assert result.status == "PARTIALLY_FILLED"


def test_poll_failed() -> None:
    client = MagicMock()
    client.get_order.side_effect = RuntimeError("offline")
    c = cfg(dry_run=False, live_trading=True, api_key="k", api_secret="s")
    result = OrderExecutor(c, client).poll("42", Decimal("0.001"))
    assert not result.ok
    assert result.reason == "poll_failed"
