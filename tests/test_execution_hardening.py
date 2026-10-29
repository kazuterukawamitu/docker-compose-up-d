from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from bitbank_bot.engine import BotState, Engine, PendingOrder, load_state, save_state
from bitbank_bot.fees import resolve_fee, tp_covers_fees
from bitbank_bot.indicators import shannon_entropy, simple_returns
from bitbank_bot.market_data import synthetic_candles
from bitbank_bot.orders import OrderExecutor, _fill_status
from bitbank_bot.reconciliation import reconcile
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import Position, Signal, Strategy
from tests.helpers import cfg


def test_fill_status_honors_canceled() -> None:
    assert _fill_status("CANCELED_UNFILLED", Decimal("0"), Decimal("1")) == "CANCELED"
    assert (
        _fill_status("CANCELED_PARTIALLY_FILLED", Decimal("0.4"), Decimal("1"))
        == "CANCELED_PARTIAL"
    )


def test_poll_canceled_clears_pending(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
        require_reconcile=False,
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
    state = BotState(
        None,
        RiskManager(c),
        0,
        0.0,
        pending=PendingOrder(
            order_id="42",
            side="buy",
            kind="BUY1",
            tp_pct=Decimal("0.03"),
            index=1,
            timestamp_ms=1,
            amount=Decimal("0.001"),
        ),
    )
    engine._poll_pending(state)
    assert state.pending is None


def test_partial_notional_uses_incremental_cost(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
        require_reconcile=False,
        enable_htf_filter=False,
        enable_fee_aware_entry=False,
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
        "status": "PARTIALLY_FILLED",
        "executed_amount": "0.8",
        "average_price": "150",
        "start_amount": "1",
        "fee_amount_quote": "0",
    }
    engine = Engine(c, client=rest)
    state = BotState(
        Position(
            amount=Decimal("0.4"),
            average_price=Decimal("100"),
            tp_pct=Decimal("0.03"),
            entry_candle_index=1,
            entry_candle_ts=1,
            actual_execution_jpy=Decimal("40"),
            kind="BUY1",
        ),
        RiskManager(c),
        0,
        0.0,
        pending=PendingOrder(
            order_id="7",
            side="buy",
            kind="BUY1",
            tp_pct=Decimal("0.03"),
            index=1,
            timestamp_ms=1,
            amount=Decimal("1"),
            filled_amount=Decimal("0.4"),
            filled_notional=Decimal("40"),  # 0.4 @ 100
        ),
    )
    engine._poll_pending(state)
    assert state.position is not None
    # Incremental notional = 0.8*150 - 40 = 80 (not 0.4*150=60) → total 120
    assert state.position.amount == Decimal("0.8")
    assert state.position.actual_execution_jpy == Decimal("120")
    assert state.pending is not None
    assert state.pending.filled_notional == Decimal("120")


def test_intrabar_tp_fires_on_heartbeat(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        dry_run=True,
        live_trading=False,
        enable_intrabar_exits=True,
        enable_htf_filter=False,
        stop_loss_pct=Decimal("0.03"),
        ma_period=3,
        short_ma_period=3,
        long_ma_period=5,
    )
    engine = Engine(c, client=MagicMock())
    candles = synthetic_candles(40)
    from bitbank_bot.strategy import build_snapshots

    snaps = build_snapshots([x.close for x in candles], [x.timestamp_ms for x in candles], c)
    last = snaps[-1]
    entry = last.close
    state = BotState(
        Position(
            amount=Decimal("0.001"),
            average_price=entry,
            tp_pct=Decimal("0.001"),
            entry_candle_index=last.index - 1,
            entry_candle_ts=last.timestamp_ms - 1,
            actual_execution_jpy=entry * Decimal("0.001"),
            kind="BUY1",
        ),
        RiskManager(c),
        last.timestamp_ms,
        0.0,
        paper_jpy=Decimal("90000"),
        paper_btc=Decimal("0.001"),
    )
    engine.last_public_last = str(entry * Decimal("1.01"))
    signal = engine.process_candles(candles, state, execute=True, persist=False)
    assert state.position is None
    assert signal.kind in {"TP", "HOLD"} or signal.side in {None, "sell"}


def test_fee_deducted_from_realized_pnl(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        dry_run=True,
        live_trading=False,
        simulate_fill=True,
        fee_buffer=Decimal("0.001"),
        enable_fee_aware_entry=False,
    )
    engine = Engine(c, client=MagicMock())
    state = BotState(
        Position(
            amount=Decimal("0.001"),
            average_price=Decimal("10000000"),
            tp_pct=Decimal("0.03"),
            entry_candle_index=1,
            entry_candle_ts=1,
            actual_execution_jpy=Decimal("10000"),
            kind="BUY1",
            fees_paid=Decimal("15"),
        ),
        RiskManager(c),
        0,
        0.0,
        paper_jpy=Decimal("90000"),
        paper_btc=Decimal("0.001"),
    )
    engine._execute(
        Signal("TP", "sell", Decimal("0.03"), "test"),
        Decimal("10300000"),
        2,
        2,
        state,
    )
    assert state.position is None
    # proceeds 10300 - cost 10000 - sell fee ~10.3 - buy fee 15
    assert state.risk.daily_pnl < Decimal("300")


def test_tp_covers_fees_gate() -> None:
    assert not tp_covers_fees(Decimal("0.002"), Decimal("0.0015"))
    assert tp_covers_fees(Decimal("0.03"), Decimal("0.0015"))


def test_reconcile_stale_pending() -> None:
    report = reconcile(
        exchange_jpy=Decimal("1"),
        exchange_btc=Decimal("0"),
        open_orders=[],
        bot_position_btc=Decimal("0"),
        pending=True,
        min_amount=Decimal("0.0001"),
    )
    assert not report.ok
    assert report.reason == "pending_without_exchange_order"


def test_shannon_entropy_bounds() -> None:
    returns = simple_returns([Decimal(str(i)) for i in range(1, 30)])
    value = shannon_entropy(returns, bins=8)
    assert Decimal("0") <= value <= Decimal("1")


def test_strategy_mark_stop() -> None:
    c = cfg(stop_loss_pct=Decimal("0.03"))
    strategy = Strategy(c)
    position = Position(
        amount=Decimal("0.001"),
        average_price=Decimal("100"),
        tp_pct=Decimal("0.05"),
        entry_candle_index=1,
        entry_candle_ts=1,
        actual_execution_jpy=Decimal("0.1"),
        kind="BUY1",
    )
    signal = strategy.evaluate_mark(Decimal("96"), position)
    assert signal.kind == "STOP"
    assert signal.side == "sell"


def test_state_persists_fees_and_notional(tmp_path) -> None:
    c = cfg(state_path=str(tmp_path / "state.json"))
    state = BotState(
        Position(
            amount=Decimal("0.001"),
            average_price=Decimal("10"),
            tp_pct=Decimal("0.03"),
            entry_candle_index=1,
            entry_candle_ts=1,
            actual_execution_jpy=Decimal("0.01"),
            kind="BUY1",
            fees_paid=Decimal("0.001"),
        ),
        RiskManager(c),
        5,
        0.0,
        pending=PendingOrder(
            order_id="1",
            side="buy",
            kind="BUY1",
            tp_pct=Decimal("0.03"),
            index=1,
            timestamp_ms=1,
            amount=Decimal("0.002"),
            filled_amount=Decimal("0.001"),
            filled_notional=Decimal("10"),
        ),
    )
    save_state(c.state_path, state)
    loaded = load_state(c.state_path, c)
    assert loaded.position is not None
    assert loaded.position.fees_paid == Decimal("0.001")
    assert loaded.pending is not None
    assert loaded.pending.filled_notional == Decimal("10")


def test_resolve_fee_prefers_raw() -> None:
    fee = resolve_fee({"fee_amount_quote": "12.5"}, Decimal("10000"), Decimal("0.001"))
    assert fee == Decimal("12.5")


def test_poll_canceled_partial_clears_when_delta_zero(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
        require_reconcile=False,
    )
    rest = MagicMock()
    rest.get_order.return_value = {
        "order_id": "99",
        "status": "CANCELED_PARTIALLY_FILLED",
        "executed_amount": "0.0004",
        "average_price": "10000000",
        "start_amount": "0.001",
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
        0.0,
        pending=PendingOrder(
            order_id="99",
            side="buy",
            kind="BUY1",
            tp_pct=Decimal("0.03"),
            index=1,
            timestamp_ms=1,
            amount=Decimal("0.001"),
            filled_amount=Decimal("0.0004"),
            filled_notional=Decimal("4000"),
        ),
    )
    engine._poll_pending(state)
    assert state.pending is None


def test_startup_reconcile_polls_filled_pending_not_stale_clear(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
        require_reconcile=True,
        enable_htf_filter=False,
    )
    rest = MagicMock()
    rest.free_amount.side_effect = lambda asset: (
        Decimal("90000") if asset == "jpy" else Decimal("0.001")
    )
    rest.get_active_orders.return_value = []
    rest.get_order.return_value = {
        "order_id": "filled-1",
        "status": "FULLY_FILLED",
        "executed_amount": "0.001",
        "average_price": "10000000",
        "start_amount": "0.001",
        "fee_amount_quote": "0",
    }
    engine = Engine(c, client=rest)
    state = BotState(
        None,
        RiskManager(c),
        0,
        0.0,
        pending=PendingOrder(
            order_id="filled-1",
            side="buy",
            kind="BUY1",
            tp_pct=Decimal("0.03"),
            index=1,
            timestamp_ms=1,
            amount=Decimal("0.001"),
            filled_amount=Decimal("0"),
            filled_notional=Decimal("0"),
        ),
    )
    engine._startup_reconcile(state)
    assert state.pending is None
    assert state.position is not None
    assert state.position.amount == Decimal("0.001")
    assert state.reconcile_ok is True
    assert engine._reconcile_blocked is False
    rest.get_order.assert_called()


def test_adopted_pending_books_filled_notional_into_position(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
        require_reconcile=True,
    )
    rest = MagicMock()
    rest.free_amount.side_effect = lambda asset: (
        Decimal("50000") if asset == "jpy" else Decimal("0.0004")
    )
    rest.get_active_orders.return_value = [
        {
            "order_id": "adopt-1",
            "side": "buy",
            "status": "PARTIALLY_FILLED",
            "start_amount": "0.001",
            "remaining_amount": "0.0006",
            "executed_amount": "0.0004",
            "average_price": "10000000",
        }
    ]
    engine = Engine(c, client=rest)
    state = BotState(None, RiskManager(c), 0, 0.0)
    engine._startup_reconcile(state)
    assert state.pending is not None
    assert state.pending.order_id == "adopt-1"
    assert state.pending.filled_amount == Decimal("0.0004")
    assert state.pending.filled_notional == Decimal("4000")
    assert state.position is not None
    assert state.position.amount == Decimal("0.0004")
    assert state.position.actual_execution_jpy == Decimal("4000")
    assert state.reconcile_ok is True


def test_adopt_refuses_without_real_mark(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
        require_reconcile=True,
        min_amount_btc=Decimal("0.0001"),
    )
    rest = MagicMock()
    rest.free_amount.side_effect = lambda asset: (
        Decimal("0") if asset == "jpy" else Decimal("0.002")
    )
    rest.get_active_orders.return_value = []
    rest.get_ticker.side_effect = RuntimeError("offline")
    engine = Engine(c, client=rest)
    engine.last_public_last = "-"
    state = BotState(None, RiskManager(c), 0, 0.0)
    engine._startup_reconcile(state)
    assert state.position is None
    assert state.reconcile_ok is False
    assert state.reconcile_reason == "adopt_mark_unavailable"
    assert engine._reconcile_blocked is True


def test_execute_blocked_when_reconcile_required(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
        require_reconcile=True,
        simulate_fill=True,
    )
    engine = Engine(c, client=MagicMock())
    engine._reconcile_blocked = True
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
        RiskManager(c),
        0,
        0.0,
        reconcile_ok=False,
        reconcile_reason="btc_position_mismatch",
        paper_jpy=Decimal("0"),
        paper_btc=Decimal("0.001"),
    )
    engine._execute(
        Signal("TP", "sell", Decimal("0.03"), "mark_tp"),
        Decimal("10300000"),
        2,
        2,
        state,
    )
    assert state.position is not None
    assert engine.last_block_reason.startswith("reconcile_")


def test_kill_flatten_runs_before_mark_tp(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        kill_switch_path=str(tmp_path / "KILL"),
        enable_websocket=False,
        dry_run=True,
        live_trading=False,
        enable_intrabar_exits=True,
        enable_htf_filter=False,
        emergency_flatten_on_kill=True,
        stop_loss_pct=Decimal("0.03"),
        ma_period=3,
        short_ma_period=3,
        long_ma_period=5,
        require_reconcile=False,
    )
    (tmp_path / "KILL").write_text("1", encoding="utf-8")
    engine = Engine(c, client=MagicMock())
    candles = synthetic_candles(40)
    from bitbank_bot.strategy import build_snapshots

    snaps = build_snapshots([x.close for x in candles], [x.timestamp_ms for x in candles], c)
    last = snaps[-1]
    entry = last.close
    risk = RiskManager(c, killed=True)
    state = BotState(
        Position(
            amount=Decimal("0.001"),
            average_price=entry,
            tp_pct=Decimal("0.001"),
            entry_candle_index=last.index - 1,
            entry_candle_ts=last.timestamp_ms - 1,
            actual_execution_jpy=entry * Decimal("0.001"),
            kind="BUY1",
        ),
        risk,
        last.timestamp_ms,
        0.0,
        paper_jpy=Decimal("90000"),
        paper_btc=Decimal("0.001"),
    )
    engine.last_public_last = str(entry * Decimal("1.01"))
    signal = engine.process_candles(candles, state, execute=True, persist=False)
    assert state.position is None
    assert signal.kind == "EMERGENCY_STOP"
