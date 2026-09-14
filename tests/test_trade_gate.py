from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from bitbank_bot.amounts import AmountPlan
from bitbank_bot.hold_tracer import NO_SETUP, HoldTracer, classify_root_cause
from bitbank_bot.orders import OrderExecutor
from bitbank_bot.strategy import Signal
from bitbank_bot.trade_signal_executor import evaluate_gate
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


def test_gate_blocks_synthetic() -> None:
    result = evaluate_gate(
        cfg(),
        Signal("BUY1", "buy", Decimal("0.03"), "t"),
        _plan(),
        market_data_real=False,
        market_data_fresh=True,
        private_api_ok=True,
        kill_switch=False,
        pending_order=False,
        open_order_count=0,
    )
    assert not result.allowed
    assert result.reason == "synthetic_market_data"


def test_gate_passes_actionable() -> None:
    result = evaluate_gate(
        cfg(),
        Signal("BUY1", "buy", Decimal("0.03"), "t"),
        _plan(),
        market_data_real=True,
        market_data_fresh=True,
        private_api_ok=True,
        kill_switch=False,
        pending_order=False,
        open_order_count=0,
    )
    assert result.allowed


def test_live_ready_would_submit_not_create_order() -> None:
    client = MagicMock()
    client.create_order.side_effect = AssertionError("live order")
    c = cfg(dry_run=True, live_trading=False, trading_mode="live_ready", simulate_fill=False)
    result = OrderExecutor(c, client).place(
        Signal("BUY1", "buy", Decimal("0.03"), "t"), _plan()
    )
    assert result.reason == "intent_only"
    client.create_order.assert_not_called()


def test_hold_tracer_no_setup() -> None:
    cause = classify_root_cause(
        signal_reason="no_buy_setup",
        block_reason="",
        market_data_real=True,
        trading_mode="dry_run",
        signal_kind="HOLD",
    )
    assert cause == NO_SETUP
    tracer = HoldTracer()
    report = tracer.note(
        signal_kind="HOLD",
        signal_reason="no_buy_setup",
        block_reason="",
        market_data_real=True,
        trading_mode="dry_run",
        uptime_sec=901,
        timeout_sec=900,
    )
    assert report is not None
    assert report.status == "STALLED"
    assert report.root_cause == NO_SETUP


def test_create_order_timeout_recovers_single_active() -> None:
    client = MagicMock()
    client.get_active_orders.side_effect = [
        [],
        [
            {
                "order_id": "7",
                "pair": "btc_jpy",
                "side": "buy",
                "status": "UNFILLED",
                "executed_amount": "0",
                "average_price": "0",
                "start_amount": "0.001",
            }
        ],
    ]
    client.create_order.side_effect = RuntimeError("ReadTimeout")
    client.get_order.return_value = {
        "order_id": "7",
        "status": "UNFILLED",
        "executed_amount": "0",
        "average_price": "0",
        "start_amount": "0.001",
    }
    c = cfg(dry_run=False, live_trading=True, api_key="k", api_secret="s")
    result = OrderExecutor(c, client).place(
        Signal("BUY1", "buy", Decimal("0.03"), "t"), _plan()
    )
    assert result.ok
    assert result.order_id == "7"
    assert result.reason == "accepted_unfilled"
    assert client.create_order.call_count == 1
