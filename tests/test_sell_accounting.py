"""SELL delay, pending, incremental fills, fee PnL, reconcile, imports.

LIVE flags appear only on mocked clients. create_order is never sent to Bitbank.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bitbank_bot.config import ConfigError, load_config
from bitbank_bot.engine import BotState, Engine, PendingOrder, load_state, save_state
from bitbank_bot.market_data import synthetic_candles
from bitbank_bot.money import incremental_fill_cost, realized_pnl_after_fees
from bitbank_bot.orders import OrderExecutor, OrderResult, extract_order_fee_jpy
from bitbank_bot.rest_client import RestClient
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import Position, Signal, Strategy, build_snapshots
from tests.helpers import cfg


def _engine(tmp_path, **overrides: object) -> tuple[Any, Engine]:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        enable_htf_filter=False,
        dry_run=True,
        live_trading=False,
        simulate_fill=True,
        ma_period=3,
        short_ma_period=3,
        long_ma_period=5,
        fee_buffer=Decimal("0.0015"),
        **overrides,
    )
    rest = MagicMock()
    rest.get_ticker.return_value = {"last": "10000000"}
    rest.create_order.side_effect = AssertionError("live order")
    rest.get_active_orders.return_value = []
    rest.free_amount.side_effect = lambda asset: (
        Decimal("100000") if asset == "jpy" else Decimal("0.001")
    )
    engine = Engine(c, client=rest)
    return c, engine


def _long_state(c, candles, *, entry_index: int = 0, last_processed: bool = True) -> BotState:
    snaps = build_snapshots(
        [x.close for x in candles], [x.timestamp_ms for x in candles], c
    )
    last = snaps[-1]
    return BotState(
        Position(
            amount=Decimal("0.001"),
            average_price=Decimal("10000000"),
            tp_pct=Decimal("0.03"),
            entry_candle_index=entry_index if entry_index else snaps[0].index,
            entry_candle_ts=1,
            actual_execution_jpy=Decimal("10000"),
            kind="BUY1",
        ),
        RiskManager(c),
        last.timestamp_ms if last_processed else 0,
        time.monotonic(),
        paper_jpy=Decimal("90000"),
        paper_btc=Decimal("0.001"),
    )


def test_required_modules_import() -> None:
    import bitbank_bot.config as config_mod
    import bitbank_bot.main as main_mod
    import bitbank_bot.rest_client as rest_mod
    import bitbank_bot.watchdog as watchdog_mod

    assert config_mod.Config is not None
    assert callable(config_mod.load_config)
    assert callable(rest_mod.RestClient)
    assert callable(main_mod.main)
    assert callable(watchdog_mod.classify)
    assert "limit" in rest_mod.BITBANK_SPOT_ORDER_TYPES
    assert "market" in rest_mod.BITBANK_SPOT_ORDER_TYPES
    assert "stop" in rest_mod.BITBANK_SPOT_ORDER_TYPES
    assert "STOP-MARKET" not in rest_mod.BITBANK_SPOT_ORDER_TYPES


def test_intrabar_tp_sells_on_already_processed_bar(tmp_path) -> None:
    c, engine = _engine(tmp_path)
    candles = synthetic_candles(40)
    state = _long_state(c, candles, last_processed=True)
    engine.client.get_ticker.return_value = {"last": "10310000"}
    with patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal.hold("candle already processed"),
    ):
        engine.process_candles(candles, state, execute=True, persist=False)
    assert state.position is None
    assert state.paper_btc == Decimal("0")
    assert state.risk.daily_pnl != Decimal("0")


def test_same_entry_candle_blocks_intrabar_tp(tmp_path) -> None:
    c, engine = _engine(tmp_path)
    candles = synthetic_candles(40)
    snaps = build_snapshots(
        [x.close for x in candles], [x.timestamp_ms for x in candles], c
    )
    state = _long_state(c, candles, entry_index=snaps[-1].index, last_processed=True)
    engine.client.get_ticker.return_value = {"last": "20000000"}
    engine.process_candles(candles, state, execute=True, persist=False)
    assert state.position is not None
    assert state.position.amount == Decimal("0.001")


def test_intrabar_protective_stop_on_ticker(tmp_path) -> None:
    c, engine = _engine(tmp_path, protective_stop_pct=Decimal("0.02"))
    candles = synthetic_candles(40)
    state = _long_state(c, candles, last_processed=True)
    engine.client.get_ticker.return_value = {"last": "9700000"}
    with patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal.hold("candle already processed"),
    ):
        engine.process_candles(candles, state, execute=True, persist=False)
    assert state.position is None
    assert state.paper_btc == Decimal("0")


def test_heartbeat_without_tp_or_stop_does_not_flatten(tmp_path) -> None:
    c, engine = _engine(tmp_path, protective_stop_pct=Decimal("0"))
    candles = synthetic_candles(40)
    state = _long_state(c, candles, last_processed=True)
    engine.client.get_ticker.return_value = {"last": "10010000"}
    with patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal.hold("candle already processed"),
    ):
        engine.process_candles(candles, state, execute=True, persist=False)
    assert state.position is not None


def test_protective_exit_stop_before_tp() -> None:
    c = cfg(protective_stop_pct=Decimal("0.02"), buy1_tp=Decimal("0.03"))
    pos = Position(
        amount=Decimal("0.001"),
        average_price=Decimal("10000000"),
        tp_pct=Decimal("0.03"),
        entry_candle_index=1,
        entry_candle_ts=1,
        actual_execution_jpy=Decimal("10000"),
        kind="BUY1",
    )
    stop = Strategy(c).protective_exit(pos, Decimal("9700000"), same_entry=False)
    assert stop.kind == "STOP"
    assert stop.side == "sell"
    same = Strategy(c).protective_exit(pos, Decimal("20000000"), same_entry=True)
    assert same.kind == "HOLD"
    assert same.reason == "same_entry_candle_no_sell"
    tp = Strategy(c).protective_exit(pos, Decimal("10310000"), same_entry=False)
    assert tp.kind == "TP"


def test_canceled_unfilled_clears_pending(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        enable_websocket=False,
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
    )
    rest = MagicMock()
    rest.get_order.return_value = {
        "order_id": "42",
        "status": "CANCELED_UNFILLED",
        "executed_amount": "0",
        "average_price": "0",
        "start_amount": "0.001",
    }
    engine = Engine(c, client=rest)
    state = BotState(None, RiskManager(c), 0, time.monotonic())
    state.pending = PendingOrder(
        order_id="42",
        side="buy",
        kind="BUY1",
        tp_pct=Decimal("0.03"),
        index=1,
        timestamp_ms=1,
        amount=Decimal("0.001"),
    )
    engine._poll_pending(state)
    assert state.pending is None
    assert state.position is None


def test_rejected_clears_pending_so_next_signal_can_fire(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        enable_htf_filter=False,
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
        ma_period=3,
        short_ma_period=3,
        long_ma_period=5,
    )
    rest = MagicMock()
    rest.free_amount.side_effect = lambda asset: (
        Decimal("100000") if asset == "jpy" else Decimal("0")
    )
    rest.get_active_orders.return_value = []
    rest.get_order.return_value = {
        "order_id": "7",
        "status": "REJECTED",
        "executed_amount": "0",
        "average_price": "0",
        "start_amount": "0.001",
    }
    rest.create_order.return_value = {
        "order_id": "8",
        "status": "FULLY_FILLED",
        "executed_amount": "0.001",
        "average_price": "10000000",
        "start_amount": "0.001",
    }
    engine = Engine(c, client=rest)
    candles = synthetic_candles(40)
    state = BotState(None, RiskManager(c), 0, time.monotonic())
    state.pending = PendingOrder(
        order_id="7",
        side="buy",
        kind="BUY1",
        tp_pct=Decimal("0.03"),
        index=1,
        timestamp_ms=1,
        amount=Decimal("0.001"),
    )
    with patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal("BUY1", "buy", Decimal("0.03"), "forced"),
    ):
        engine.process_candles(candles, state, execute=True, persist=False)
    assert state.pending is None
    assert state.position is not None
    rest.create_order.assert_called_once()


def test_canceled_partial_books_incremental_then_clears(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
        enable_websocket=False,
    )
    rest = MagicMock()
    rest.free_amount.side_effect = lambda asset: (
        Decimal("100000") if asset == "jpy" else Decimal("0")
    )
    rest.get_order.return_value = {
        "order_id": "99",
        "status": "CANCELED_PARTIALLY_FILLED",
        "executed_amount": "0.0004",
        "average_price": "10000000",
        "start_amount": "0.001",
    }
    engine = Engine(c, client=rest)
    state = BotState(None, RiskManager(c), 0, time.monotonic())
    state.pending = PendingOrder(
        order_id="99",
        side="buy",
        kind="BUY1",
        tp_pct=Decimal("0.03"),
        index=1,
        timestamp_ms=1,
        amount=Decimal("0.001"),
        filled_amount=Decimal("0"),
        filled_cost=Decimal("0"),
    )
    engine._poll_pending(state)
    assert state.pending is None
    assert state.position is not None
    assert state.position.amount == Decimal("0.0004")
    assert state.position.actual_execution_jpy == Decimal("4000")


def test_incremental_fill_cost_not_avg_times_delta() -> None:
    # First 0.4 @ 10_000_000 = 4_000. Second 0.6 @ 11_000_000 = 6_600.
    # Cumulative avg = 10_600. Wrong booking is 0.6 * 10_600 = 6_360.
    incremental = incremental_fill_cost(
        prev_qty=Decimal("0.0004"),
        prev_cost=Decimal("4000"),
        new_qty=Decimal("0.001"),
        new_avg=Decimal("10600000"),
    )
    assert incremental == Decimal("6600")
    assert incremental != Decimal("0.0006") * Decimal("10600000")


def test_partial_poll_uses_incremental_jpy(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
        enable_websocket=False,
    )
    rest = MagicMock()
    rest.free_amount.side_effect = lambda asset: (
        Decimal("100000") if asset == "jpy" else Decimal("0")
    )
    rest.get_order.return_value = {
        "order_id": "55",
        "status": "PARTIALLY_FILLED",
        "executed_amount": "0.001",
        "average_price": "10600000",
        "start_amount": "0.002",
    }
    engine = Engine(c, client=rest)
    state = BotState(
        Position(
            amount=Decimal("0.0004"),
            average_price=Decimal("10000000"),
            tp_pct=Decimal("0.03"),
            entry_candle_index=1,
            entry_candle_ts=1,
            actual_execution_jpy=Decimal("4000"),
            kind="BUY1",
        ),
        RiskManager(c),
        0,
        time.monotonic(),
    )
    state.pending = PendingOrder(
        order_id="55",
        side="buy",
        kind="BUY1",
        tp_pct=Decimal("0.03"),
        index=1,
        timestamp_ms=1,
        amount=Decimal("0.002"),
        filled_amount=Decimal("0.0004"),
        filled_cost=Decimal("4000"),
    )
    engine._poll_pending(state)
    assert state.pending is not None
    assert state.pending.filled_amount == Decimal("0.001")
    assert state.pending.filled_cost == Decimal("10600")
    assert state.position is not None
    assert state.position.actual_execution_jpy == Decimal("10600")
    assert state.position.amount == Decimal("0.001")


def test_realized_pnl_deducts_fee_buffer() -> None:
    pnl = realized_pnl_after_fees(
        proceeds=Decimal("10300"),
        cost=Decimal("10000"),
        fee_buffer=Decimal("0.0015"),
    )
    assert pnl == Decimal("10300") - Decimal("10000") - Decimal("15") - Decimal("15.45")


def test_realized_pnl_prefers_actual_fees() -> None:
    pnl = realized_pnl_after_fees(
        proceeds=Decimal("10300"),
        cost=Decimal("10000"),
        fee_buffer=Decimal("0.0015"),
        buy_fee=Decimal("10"),
        sell_fee=Decimal("12"),
    )
    assert pnl == Decimal("278")


def test_sell_apply_fill_deducts_fees_from_daily_pnl(tmp_path) -> None:
    c, engine = _engine(tmp_path)
    state = BotState(
        Position(
            amount=Decimal("0.001"),
            average_price=Decimal("10000000"),
            tp_pct=Decimal("0.03"),
            entry_candle_index=1,
            entry_candle_ts=1,
            actual_execution_jpy=Decimal("10000"),
            kind="BUY1",
            entry_fee_jpy=Decimal("15"),
        ),
        RiskManager(c),
        0,
        time.monotonic(),
        paper_jpy=Decimal("90000"),
        paper_btc=Decimal("0.001"),
    )
    result = OrderResult(
        True,
        "fill",
        True,
        True,
        "dry-run",
        "FULLY_FILLED",
        Decimal("0.001"),
        Decimal("10300000"),
        Decimal("10300"),
        {"fee_amount_quote": "15.45"},
        Decimal("15.45"),
    )
    plan = MagicMock()
    plan.target_jpy = Decimal("10300")
    plan.planned_order_jpy = Decimal("10300")
    plan.amount = Decimal("0.001")
    engine._apply_fill(
        Signal("TP", "sell", Decimal("0.03"), "tp"),
        plan,
        result,
        2,
        2,
        state,
        Decimal("90000"),
        Decimal("0.001"),
    )
    assert state.position is None
    assert state.risk.daily_pnl == Decimal("269.55")


def test_extract_fee_from_bitbank_trade_fields() -> None:
    assert extract_order_fee_jpy({"fee_amount_quote": "12.5"}) == Decimal("12.5")
    assert extract_order_fee_jpy({"fee_occurred_amount_quote": "3"}) == Decimal("3")
    assert extract_order_fee_jpy({}) is None


def test_reconcile_logs_not_verified_without_private_path(tmp_path) -> None:
    c, engine = _engine(tmp_path, api_key="", api_secret="")
    state = load_state(c.state_path, c)
    reason = engine.reconcile_startup(state)
    assert reason == "NOT_VERIFIED"


def test_reconcile_polls_persisted_pending(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
        enable_websocket=False,
    )
    rest = MagicMock()
    rest.get_active_orders.return_value = []
    rest.free_amount.side_effect = lambda asset: (
        Decimal("90000") if asset == "jpy" else Decimal("0.001")
    )
    rest.get_order.return_value = {
        "order_id": "42",
        "status": "FULLY_FILLED",
        "executed_amount": "0.001",
        "average_price": "10000000",
        "start_amount": "0.001",
    }
    engine = Engine(c, client=rest)
    state = BotState(None, RiskManager(c), 0, time.monotonic())
    state.pending = PendingOrder(
        order_id="42",
        side="buy",
        kind="BUY1",
        tp_pct=Decimal("0.03"),
        index=1,
        timestamp_ms=1,
        amount=Decimal("0.001"),
    )
    save_state(c.state_path, state)
    loaded = load_state(c.state_path, c)
    reason = engine.reconcile_startup(loaded)
    assert reason == "ok"
    assert loaded.pending is None
    assert loaded.position is not None
    assert loaded.position.actual_execution_jpy == Decimal("10000")


def test_pending_roundtrip_includes_filled_cost(tmp_path) -> None:
    c = cfg(state_path=str(tmp_path / "state.json"))
    state = BotState(None, RiskManager(c), 0, time.monotonic())
    state.pending = PendingOrder(
        order_id="1",
        side="buy",
        kind="BUY1",
        tp_pct=Decimal("0.03"),
        index=1,
        timestamp_ms=1,
        amount=Decimal("0.001"),
        filled_amount=Decimal("0.0004"),
        filled_cost=Decimal("4000"),
    )
    save_state(c.state_path, state)
    loaded = load_state(c.state_path, c)
    assert loaded.pending is not None
    assert loaded.pending.filled_cost == Decimal("4000")
    raw = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert raw["pending"]["filled_cost"] == "4000"


def test_order_type_rejects_invented_stop_market_name() -> None:
    with pytest.raises(ConfigError, match="ORDER_TYPE"):
        load_config(environ={"ORDER_TYPE": "STOP-MARKET"}, load_default_dotenv=False)


def test_create_order_can_send_documented_stop(tmp_path) -> None:
    http = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "success": 1,
        "data": {"order_id": 1, "status": "INACTIVE", "type": "stop"},
    }
    http.request.return_value = response
    client = RestClient(
        "https://public.example",
        "https://private.example",
        api_key="k",
        api_secret="s",
        http=http,
        max_retries=1,
    )
    try:
        client.create_order(
            "btc_jpy",
            "0.001",
            "sell",
            "stop",
            trigger_price="9700000",
            live_confirmed=True,
        )
    finally:
        client.close()
    content = http.request.call_args.kwargs["content"]
    body = json.loads(content.decode("utf-8"))
    assert body["type"] == "stop"
    assert body["trigger_price"] == "9700000"
    assert body["type"] != "STOP-MARKET"


def test_live_stop_signal_uses_market_not_invented_type() -> None:
    from bitbank_bot.amounts import AmountPlan

    client = MagicMock()
    client.get_active_orders.return_value = []
    client.create_order.return_value = {
        "order_id": "1",
        "status": "FULLY_FILLED",
        "executed_amount": "0.001",
        "average_price": "9700000",
        "start_amount": "0.001",
    }
    c = cfg(
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
        order_type="limit",
    )
    plan = AmountPlan(
        side="sell",
        amount=Decimal("0.001"),
        price=Decimal("9700000"),
        available_jpy=Decimal("0"),
        available_btc=Decimal("0.001"),
        target_jpy=Decimal("9700"),
        planned_order_jpy=Decimal("9700"),
        actual_execution_jpy=None,
        actual_balance_jpy=Decimal("0"),
        actual_balance_btc=Decimal("0.001"),
        ok=True,
        reason="ok",
    )
    result = OrderExecutor(c, client).place(Signal("STOP", "sell", None, "stop"), plan)
    assert result.ok
    kwargs = client.create_order.call_args.kwargs
    assert kwargs["order_type"] == "market"
    assert kwargs["price"] is None
    assert kwargs["live_confirmed"] is True


def test_default_protective_stop_is_off() -> None:
    loaded = load_config(environ={}, load_default_dotenv=False)
    assert loaded.protective_stop_pct == Decimal("0")
    assert loaded.exchange_stop_orders is False
