from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import httpx

from bitbank_bot.engine import PendingOrder
from bitbank_bot.engine_state import BotState
from bitbank_bot.exchange import BitbankAdapter
from bitbank_bot.managers import ExecutionMonitor, StateManager
from bitbank_bot.orders import OrderExecutor
from bitbank_bot.rest_client import BitbankAPIError, RestClient
from bitbank_bot.self_healing import ErrorClass, QuarantineManager, SelfHealingEngine, TaskSupervisor
from bitbank_bot.strategy import Signal
from bitbank_bot.trade_state import TradePhase, TradeStateMachine
from tests.helpers import cfg, risk
from tests.test_orders import _plan


class FakeHttp:
    def __init__(self, responses=None, error=None) -> None:
        self.n = 0
        self.responses = list(responses or [])
        self.error = error

    def request(self, method, url, headers=None, content=None):
        self.n += 1
        if self.error is not None:
            raise self.error
        if not self.responses:
            raise AssertionError("unexpected request")
        return self.responses.pop(0)

    def close(self) -> None:
        return None


class FakeResponse:
    def __init__(self, status_code: int, payload) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def test_adapter_forwards_create_order_only_when_confirmed() -> None:
    rest = MagicMock()
    rest.create_order.return_value = {"order_id": "9"}
    adapter = BitbankAdapter(rest)
    adapter.create_order(
        "btc_jpy", "0.001", "buy", "limit", "10000000", live_confirmed=True
    )
    rest.create_order.assert_called_once()
    assert rest.create_order.call_args.kwargs["live_confirmed"] is True


def test_adapter_active_orders_always_list() -> None:
    rest = MagicMock()
    rest.get_active_orders.return_value = None
    assert BitbankAdapter(rest).get_active_orders("btc_jpy") == []


def test_get_active_orders_non_list_payload() -> None:
    class Payload:
        def request(self, method, url, headers=None, content=None):
            return FakeResponse(200, {"success": 1, "data": {"orders": {"order_id": "1"}}})

        def close(self) -> None:
            return None

    client = RestClient(
        "https://public.example",
        "https://private.example",
        "k",
        "s",
        http=Payload(),  # type: ignore[arg-type]
    )
    try:
        assert client.get_active_orders("btc_jpy") == []
    finally:
        client.close()


def test_http_429_retries_then_ok() -> None:
    http = FakeHttp(
        responses=[
            FakeResponse(429, "rate"),
            FakeResponse(200, {"success": 1, "data": {"last": "1"}}),
        ]
    )
    client = RestClient(
        "https://public.example",
        "https://private.example",
        http=http,  # type: ignore[arg-type]
        max_retries=3,
    )
    try:
        data = client.get_ticker("btc_jpy")
        assert data["last"] == "1"
        assert http.n == 2
    finally:
        client.close()


def test_http_500_retries_then_raises() -> None:
    http = FakeHttp(responses=[FakeResponse(500, "boom"), FakeResponse(500, "boom")])
    client = RestClient(
        "https://public.example",
        "https://private.example",
        http=http,  # type: ignore[arg-type]
        max_retries=2,
    )
    try:
        raised = False
        try:
            client.get_ticker("btc_jpy")
        except BitbankAPIError as exc:
            raised = True
            assert exc.http_status == 500
        assert raised
        assert http.n == 2
    finally:
        client.close()


def test_cancel_order_is_not_retried() -> None:
    http = FakeHttp(error=httpx.TimeoutException("timeout"))
    client = RestClient(
        "https://public.example",
        "https://private.example",
        "k",
        "s",
        http=http,  # type: ignore[arg-type]
        max_retries=5,
    )
    try:
        raised = False
        try:
            client.cancel_order("btc_jpy", "1", live_confirmed=True)
        except BitbankAPIError:
            raised = True
        assert raised
        assert http.n == 1
    finally:
        client.close()


def test_cancel_order_refuses_without_confirm() -> None:
    client = RestClient("https://public.example", "https://private.example", "k", "s")
    try:
        raised = False
        try:
            client.cancel_order("btc_jpy", "1")
        except BitbankAPIError as exc:
            raised = True
            assert "live_confirmed" in str(exc)
        assert raised
    finally:
        client.close()


def test_live_cancel_calls_client() -> None:
    client = MagicMock()
    client.cancel_order.return_value = {"order_id": "1"}
    c = cfg(dry_run=False, live_trading=True, api_key="k", api_secret="s")
    assert OrderExecutor(c, client).cancel("1") is True
    client.cancel_order.assert_called_once()


def test_dry_run_cancel_does_not_call_client() -> None:
    client = MagicMock()
    c = cfg(dry_run=True)
    assert OrderExecutor(c, client).cancel("1") is False
    client.cancel_order.assert_not_called()


def test_none_price_blocked() -> None:
    client = MagicMock()
    client.create_order.side_effect = AssertionError("live order")
    plan = _plan()
    plan.price = None  # type: ignore[assignment]
    result = OrderExecutor(cfg(), client).place(Signal("BUY1", "buy", Decimal("0.03"), "t"), plan)
    assert result.ok is False
    assert result.reason == "number_expected"
    client.create_order.assert_not_called()


def test_trade_state_machine() -> None:
    machine = TradeStateMachine()
    assert machine.phase is TradePhase.WAIT
    machine.transition(TradePhase.SIGNAL_FOUND, reason="BUY1")
    assert machine.phase is TradePhase.SIGNAL_FOUND
    machine.from_bot(pending=False, in_position=False, side="buy")
    assert machine.phase is TradePhase.ENTRY_READY
    machine.from_bot(pending=True, in_position=False, side="buy")
    assert machine.phase is TradePhase.PENDING
    machine.from_bot(pending=False, in_position=True, side=None)
    assert machine.phase is TradePhase.POSITION
    machine.from_bot(pending=False, in_position=False, side=None)
    assert machine.phase is TradePhase.FLAT


def test_quarantine_and_supervisor() -> None:
    healing = SelfHealingEngine()
    for _ in range(8):
        healing.on_error("order", TimeoutError("x"))
    assert healing.quarantine.is_quarantined("order")
    supervisor = TaskSupervisor(healing)
    raised = False
    try:
        supervisor.run("order", lambda: 1)
    except RuntimeError as exc:
        raised = True
        assert "quarantined" in str(exc)
    assert raised
    healing.on_success("order")
    assert healing.quarantine.is_quarantined("order") is False
    assert supervisor.run("order", lambda: 7) == 7


def test_state_manager_roundtrip(tmp_path) -> None:
    c = cfg(state_path=str(tmp_path / "state.json"))
    mgr = StateManager(c)
    state = BotState(None, risk(c), 0, 0.0)
    state.pending = PendingOrder(
        order_id="42",
        side="buy",
        kind="BUY1",
        tp_pct=Decimal("0.03"),
        index=1,
        timestamp_ms=1,
        amount=Decimal("0.001"),
    )
    mgr.save(state)
    loaded = mgr.load()
    assert loaded.pending is not None
    assert loaded.pending.order_id == "42"


def test_execution_monitor_counts_list_not_dict() -> None:
    client = MagicMock()
    client.get_active_orders.return_value = {"order_id": "1"}
    monitor = ExecutionMonitor(cfg(), client)
    assert monitor.open_order_count() == 0


def test_classify_429_recoverable() -> None:
    from bitbank_bot.self_healing import classify_error

    assert classify_error(reason="429 rate limited") == ErrorClass.RECOVERABLE


def test_kill_cancels_pending_live_order() -> None:
    import time

    from bitbank_bot.engine import Engine
    from bitbank_bot.market_data import synthetic_candles
    from bitbank_bot.risk import RiskManager

    c = cfg(
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
        kill_switch=True,
        enable_websocket=False,
        enable_htf_filter=False,
    )
    rest = MagicMock()
    rest.cancel_order.return_value = {"order_id": "42"}
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
    engine.process_candles(synthetic_candles(40), state, execute=True, persist=False)
    rest.cancel_order.assert_called_once()
    assert rest.cancel_order.call_args.kwargs["live_confirmed"] is True
    assert state.pending is None
    rest.create_order.assert_not_called()


def test_circuit_open_blocks_new_live_order() -> None:
    import time
    from unittest.mock import patch

    from bitbank_bot.engine import Engine
    from bitbank_bot.market_data import synthetic_candles
    from bitbank_bot.risk import RiskManager

    c = cfg(
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
        enable_websocket=False,
        enable_htf_filter=False,
        ma_period=3,
        short_ma_period=3,
        long_ma_period=5,
    )
    rest = MagicMock()
    rest.create_order.side_effect = AssertionError("live order")
    rest.get_active_orders.return_value = []
    rest.free_amount.return_value = Decimal("100000")
    engine = Engine(c, client=rest)
    for _ in range(5):
        engine.healing.breaker.failure()
    state = BotState(None, RiskManager(c), 0, time.monotonic())
    with patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal("BUY1", "buy", Decimal("0.03"), "forced"),
    ):
        engine.process_candles(synthetic_candles(40), state, execute=True, persist=False)
    rest.create_order.assert_not_called()
    assert engine.last_block_reason == "circuit_open"


def test_start_sh_refuses_run_py_when_live() -> None:
    from pathlib import Path

    text = Path(__file__).resolve().parents[1].joinpath("start.sh").read_text(encoding="utf-8")
    assert "refusing run.py fallback" in text
    assert "create_order" in text
