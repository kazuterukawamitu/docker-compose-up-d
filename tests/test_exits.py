from __future__ import annotations

import time
from decimal import Decimal
from unittest.mock import MagicMock, patch

from bitbank_bot.engine import BotState, Engine, PendingOrder
from bitbank_bot.market_data import synthetic_candles
from bitbank_bot.money import ZERO
from bitbank_bot.orders import OrderResult
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import Position, Signal
from tests.helpers import cfg


def _live(tmp_path, **overrides: object):
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
        **overrides,
    )
    rest = MagicMock()
    rest.free_amount.side_effect = lambda asset: (
        Decimal("100000") if asset == "jpy" else Decimal("0.001")
    )
    rest.get_active_orders.return_value = []
    rest.create_order.return_value = {
        "order_id": "1",
        "status": "FULLY_FILLED",
        "executed_amount": "0.001",
        "average_price": "10000000",
        "start_amount": "0.001",
    }
    return c, rest, Engine(c, client=rest)


def test_second_partial_books_incremental_notional(tmp_path) -> None:
    c, rest, engine = _live(tmp_path)
    state = BotState(
        Position(
            amount=Decimal("0.0004"),
            average_price=Decimal("10000000"),
            tp_pct=Decimal("0.03"),
            entry_candle_index=1,
            entry_candle_ts=1,
            actual_execution_jpy=Decimal("4000"),
            kind="BUY1",
            fees_jpy=Decimal("4.8"),
        ),
        RiskManager(c),
        0,
        time.monotonic(),
        pending=PendingOrder(
            order_id="99",
            side="buy",
            kind="BUY1",
            tp_pct=Decimal("0.03"),
            index=1,
            timestamp_ms=1,
            amount=Decimal("0.0007"),
            filled_amount=Decimal("0.0004"),
            placed_at=time.time(),
            average_price=Decimal("10000000"),
        ),
    )
    cumulative_avg = Decimal("7300") / Decimal("0.0007")
    rest.get_order.return_value = {
        "order_id": "99",
        "status": "FULLY_FILLED",
        "executed_amount": "0.0007",
        "average_price": str(cumulative_avg),
        "start_amount": "0.0007",
    }
    candles = synthetic_candles(40)
    state.last_candle_ts = candles[-1].timestamp_ms
    with patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal("HOLD", None, None, "heartbeat"),
    ):
        engine.process_candles(candles, state, execute=True, persist=False)
    assert state.position is not None
    assert state.position.amount == Decimal("0.0007")
    assert state.position.actual_execution_jpy == Decimal("7300")
    assert state.pending is None


def test_fee_is_deducted_from_pnl_not_gross_notional(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        dry_run=True,
        taker_fee_rate=Decimal("0.0012"),
    )
    engine = Engine(c)
    state = BotState(None, RiskManager(c), 0, time.monotonic(), paper_jpy=Decimal("100000"))
    buy = OrderResult(
        True,
        "simulated",
        True,
        True,
        "dry-run",
        "FULLY_FILLED",
        Decimal("0.001"),
        Decimal("10000000"),
        Decimal("10000"),
        None,
    )
    engine._apply_fill(
        Signal("BUY1", "buy", Decimal("0.03"), "forced"),
        MagicMock(target_jpy=ZERO, planned_order_jpy=ZERO, amount=Decimal("0.001")),
        buy,
        1,
        1,
        state,
        Decimal("100000"),
        ZERO,
    )
    assert state.position is not None
    assert state.position.actual_execution_jpy == Decimal("10000")
    assert state.position.fees_jpy == Decimal("12")
    assert state.paper_jpy == Decimal("89988")
    sell = OrderResult(
        True,
        "simulated",
        True,
        True,
        "dry-run",
        "FULLY_FILLED",
        Decimal("0.001"),
        Decimal("10300000"),
        Decimal("10300"),
        None,
    )
    engine._apply_fill(
        Signal("TP", "sell", Decimal("0.03"), "forced"),
        MagicMock(target_jpy=ZERO, planned_order_jpy=ZERO, amount=Decimal("0.001")),
        sell,
        2,
        2,
        state,
        state.paper_jpy,
        Decimal("0.001"),
    )
    assert state.position is None
    assert state.risk.daily_pnl == Decimal("275.64")


def test_live_mark_stop_is_a_market_order(tmp_path) -> None:
    _c, rest, engine = _live(tmp_path)
    candles = synthetic_candles(40)
    state = BotState(
        Position(
            amount=Decimal("0.001"),
            average_price=Decimal("10000000"),
            tp_pct=Decimal("0.03"),
            entry_candle_index=1,
            entry_candle_ts=1,
            actual_execution_jpy=Decimal("10000"),
            kind="BUY1",
        ),
        RiskManager(_c),
        candles[-1].timestamp_ms,
        time.monotonic(),
    )
    engine.last_public_last = "9600000"
    engine.last_quote_ms = int(time.time() * 1000)
    rest.create_order.return_value = {
        "order_id": "stop-1",
        "status": "FULLY_FILLED",
        "executed_amount": "0.001",
        "average_price": "9600000",
        "start_amount": "0.001",
    }
    with patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal("HOLD", None, None, "should_not_run"),
    ) as evaluate:
        engine.process_candles(candles, state, execute=True, persist=False)
    evaluate.assert_not_called()
    assert rest.create_order.call_args.kwargs["order_type"] == "market"
    assert rest.create_order.call_args.kwargs["side"] == "sell"
    assert Decimal(rest.create_order.call_args.kwargs["amount"]) == Decimal("0.001")
    assert state.position is None


def test_fee_edge_and_entropy_block_buys_only(tmp_path) -> None:
    _c, rest, engine = _live(tmp_path)
    candles = synthetic_candles(40)
    state = BotState(None, RiskManager(_c), 0, time.monotonic())
    with patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal("BUY1", "buy", Decimal("0.001"), "too_small"),
    ):
        engine.process_candles(candles, state, execute=True, persist=False)
    assert engine.last_block_reason == "fee_edge"
    rest.create_order.assert_not_called()

    engine._returns = [Decimal("-0.02")] * 8
    state = BotState(None, RiskManager(_c), 0, time.monotonic())
    with patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal("BUY1", "buy", Decimal("0.03"), "forced"),
    ):
        engine.process_candles(candles, state, execute=True, persist=False)
    assert engine.last_block_reason == "posterior_down"
    rest.create_order.assert_not_called()


def test_reconcile_clears_adopts_and_does_not_sell_extra_btc(tmp_path) -> None:
    c, rest, engine = _live(tmp_path)
    engine._explicit_synthetic = False
    state = BotState(
        None,
        RiskManager(c),
        0,
        time.monotonic(),
        pending=PendingOrder(
            order_id="7",
            side="buy",
            kind="BUY1",
            tp_pct=Decimal("0.03"),
            index=1,
            timestamp_ms=1,
            amount=Decimal("0.001"),
            placed_at=time.time(),
        ),
    )
    rest.get_active_orders.return_value = []
    rest.get_order.return_value = {"order_id": "7", "status": "CANCELED_UNFILLED"}
    engine.reconcile(state)
    assert state.pending is None

    rest.get_active_orders.return_value = [
        {"order_id": "9", "side": "buy", "start_amount": "0.001", "executed_amount": "0"}
    ]
    engine.reconcile(state)
    assert state.pending is not None
    assert state.pending.order_id == "9"
    rest.create_order.assert_not_called()

    state.pending = None
    state.position = Position(
        amount=Decimal("0.001"),
        average_price=Decimal("10000000"),
        tp_pct=Decimal("0.03"),
        entry_candle_index=1,
        entry_candle_ts=1,
        actual_execution_jpy=Decimal("10000"),
        kind="BUY1",
    )
    rest.free_amount.side_effect = lambda asset: (
        Decimal("100000") if asset == "jpy" else Decimal("0.002")
    )
    rest.get_active_orders.return_value = []
    engine.reconcile(state)
    assert state.position.amount == Decimal("0.001")
    rest.create_order.assert_not_called()
