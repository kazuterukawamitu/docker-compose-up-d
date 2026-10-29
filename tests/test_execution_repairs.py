from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from bitbank_bot.engine import BotState, Engine, PendingOrder
from bitbank_bot.market_data import synthetic_candles
from bitbank_bot.money import D, ZERO
from bitbank_bot.orders import OrderResult
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import Position, Signal
from tests.helpers import cfg


def _position() -> Position:
    return Position(
        amount=D("0.001"),
        average_price=D("10000000"),
        tp_pct=D("0.03"),
        entry_candle_index=1,
        entry_candle_ts=1,
        actual_execution_jpy=D("10000"),
        kind="BUY1",
        fee_jpy=D("10"),
    )


def _engine(tmp_path, **overrides: object) -> Engine:
    params: dict[str, object] = dict(
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
    )
    params.update(overrides)
    return Engine(cfg(**params), client=MagicMock())


def test_heartbeat_take_profit_sells_without_a_new_candle(tmp_path) -> None:
    engine = _engine(tmp_path)
    candles = synthetic_candles(40)
    state = BotState(
        _position(),
        RiskManager(engine.cfg),
        candles[-1].timestamp_ms,
        0.0,
        paper_jpy=D("90000"),
        paper_btc=D("0.001"),
    )
    engine.last_public_last = "11000000"
    with patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal.hold("in_position_no_sell_or_tp"),
    ):
        signal = engine.process_candles(candles, state, execute=True, persist=False)
    assert signal.kind == "TP"
    assert state.position is None
    assert state.risk.daily_pnl == D("11000") - D("11000") * D("0.0012") - D("10000") - D("10")
    assert state.paper_jpy > D("90000")


def test_canceled_pending_does_not_block_the_next_decision(tmp_path) -> None:
    engine = _engine(
        tmp_path,
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
    )
    rest = engine.client
    rest.free_amount.side_effect = lambda asset: D("100000") if asset == "jpy" else D("0")
    rest.get_active_orders.return_value = []
    rest.get_order.return_value = {
        "order_id": "42",
        "status": "CANCELED_UNFILLED",
        "executed_amount": "0",
        "average_price": "0",
        "start_amount": "0.001",
    }
    state = BotState(
        None,
        RiskManager(engine.cfg),
        0,
        0.0,
        pending=PendingOrder(
            order_id="42",
            side="buy",
            kind="BUY1",
            tp_pct=D("0.03"),
            index=1,
            timestamp_ms=1,
            amount=D("0.001"),
        ),
    )
    with patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal.hold("no_buy_setup"),
    ):
        engine.process_candles(synthetic_candles(40), state, execute=True, persist=False)
    assert state.pending is None
    rest.create_order.assert_not_called()


def test_second_partial_uses_incremental_notional(tmp_path) -> None:
    engine = _engine(
        tmp_path,
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
    )
    rest = engine.client
    rest.free_amount.side_effect = lambda asset: D("100000") if asset == "jpy" else D("0.0004")
    rest.get_order.return_value = {
        "order_id": "99",
        "status": "PARTIALLY_FILLED",
        "executed_amount": "0.0008",
        "average_price": "11000000",
        "start_amount": "0.001",
        "fee_amount_quote": "0",
    }
    candles = synthetic_candles(40)
    engine.last_public_last = "11000000"
    state = BotState(
        Position(
            amount=D("0.0004"),
            average_price=D("10000000"),
            tp_pct=D("0.03"),
            entry_candle_index=1,
            entry_candle_ts=1,
            actual_execution_jpy=D("4000"),
            kind="BUY1",
        ),
        RiskManager(engine.cfg),
        candles[-1].timestamp_ms,
        0.0,
        pending=PendingOrder(
            order_id="99",
            side="buy",
            kind="BUY1",
            tp_pct=D("0.03"),
            index=1,
            timestamp_ms=1,
            amount=D("0.001"),
            filled_amount=D("0.0004"),
            filled_notional=D("4000"),
        ),
    )
    with patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal.hold("pending_fill"),
    ):
        engine.process_candles(candles, state, execute=True, persist=False)
    assert state.position is not None
    assert state.position.amount == D("0.0008")
    assert state.position.actual_execution_jpy == D("8800")
    assert state.pending is not None
    assert state.pending.filled_amount == D("0.0008")
    assert state.pending.filled_notional == D("8800")


def test_reconcile_adopts_exchange_btc_and_ignores_dry_run(tmp_path) -> None:
    dry = _engine(tmp_path)
    dry_state = BotState(None, RiskManager(dry.cfg), 0, 0.0)
    dry.reconcile(dry_state)
    dry.client.free_amount.assert_not_called()
    assert dry_state.position is None

    live = _engine(
        tmp_path,
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
    )
    live.client.free_amount.side_effect = lambda asset: D("50000") if asset == "jpy" else D("0.01")
    live.client.get_active_orders.return_value = []
    live.client.get_trade_history.return_value = [
        {
            "side": "buy",
            "amount": "0.01",
            "price": "10000000",
            "fee_amount_quote": "100",
            "executed_at": 10,
            "order_id": "1",
        }
    ]
    state = BotState(None, RiskManager(live.cfg), 0, 0.0)
    live.reconcile(state)
    assert state.position is not None
    assert state.position.kind == "RECONCILED"
    assert state.position.amount == D("0.01")
    assert state.position.average_price == D("10000000")
    assert state.position.fee_jpy == D("100")


def test_dry_run_with_keys_sells_from_paper_not_exchange(tmp_path) -> None:
    engine = _engine(
        tmp_path,
        dry_run=True,
        live_trading=False,
        api_key="k",
        api_secret="s",
        simulate_fill=True,
    )
    rest = engine.client
    rest.free_amount.side_effect = lambda asset: D("100000") if asset == "jpy" else D("0")
    rest.get_active_orders.return_value = []
    candles = synthetic_candles(40)
    state = BotState(
        _position(),
        RiskManager(engine.cfg),
        0,
        0.0,
        paper_jpy=D("90000"),
        paper_btc=D("0.001"),
    )
    with patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal("SELL1", "sell", None, "test_sell"),
    ):
        signal = engine.process_candles(candles, state, execute=True, persist=False)
    assert signal.kind == "SELL1"
    assert state.position is None
    assert state.paper_btc == ZERO
    rest.create_order.assert_not_called()
    rest.free_amount.assert_not_called()


def test_pattern_sell_releases_pending_buy(tmp_path) -> None:
    engine = _engine(
        tmp_path,
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
        enable_protective_exits=False,
    )
    rest = engine.client
    rest.free_amount.side_effect = lambda asset: D("50000") if asset == "jpy" else D("0.001")
    rest.get_active_orders.return_value = []
    open_order = {
        "order_id": "42",
        "status": "UNFILLED",
        "executed_amount": "0",
        "average_price": "0",
        "start_amount": "0.001",
    }
    canceled = {
        "order_id": "42",
        "status": "CANCELED_UNFILLED",
        "executed_amount": "0",
        "average_price": "0",
        "start_amount": "0.001",
    }
    # First poll keeps pending open; cancel + follow-up poll clear it.
    rest.get_order.side_effect = [open_order, canceled]
    rest.cancel_order.return_value = canceled
    rest.create_order.return_value = {
        "order_id": "99",
        "status": "FULLY_FILLED",
        "executed_amount": "0.001",
        "average_price": "10000000",
        "start_amount": "0.001",
        "fee_amount_quote": "12",
    }
    candles = synthetic_candles(40)
    state = BotState(
        _position(),
        RiskManager(engine.cfg),
        0,
        0.0,
        pending=PendingOrder(
            order_id="42",
            side="buy",
            kind="BUY1",
            tp_pct=D("0.03"),
            index=1,
            timestamp_ms=1,
            amount=D("0.001"),
        ),
    )
    with patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal("SELL1", "sell", None, "pattern_sell"),
    ):
        signal = engine.process_candles(candles, state, execute=True, persist=False)
    assert signal.kind == "SELL1"
    assert state.position is None
    assert state.pending is None
    rest.cancel_order.assert_called()
    rest.create_order.assert_called()
    assert rest.create_order.call_args.kwargs.get("side") == "sell"


def test_apply_fill_sell_subtracts_both_fees(tmp_path) -> None:
    engine = _engine(tmp_path)
    state = BotState(_position(), RiskManager(engine.cfg), 0, 0.0, paper_jpy=D("90000"), paper_btc=D("0.001"))
    result = OrderResult(
        True,
        "simulated",
        True,
        True,
        "dry-run",
        "FULLY_FILLED",
        D("0.001"),
        D("11000000"),
        D("11000"),
        None,
        D("13.2"),
        D("0"),
        False,
    )
    from bitbank_bot.amounts import AmountPlan

    plan = AmountPlan(
        side="sell",
        amount=D("0.001"),
        price=D("11000000"),
        available_jpy=D("90000"),
        available_btc=D("0.001"),
        target_jpy=D("11000"),
        planned_order_jpy=D("11000"),
        actual_execution_jpy=None,
        actual_balance_jpy=D("90000"),
        actual_balance_btc=D("0.001"),
        ok=True,
        reason="ok",
    )
    engine._apply_fill(Signal("TP", "sell", D("0.03"), "tp"), plan, result, 2, 2, state, D("90000"), D("0.001"))
    assert state.position is None
    assert state.risk.daily_pnl == D("976.8")
    assert state.paper_jpy == D("90000") + D("11000") - D("13.2")
