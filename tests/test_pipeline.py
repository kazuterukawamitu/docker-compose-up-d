"""Integration-style pipeline: signal → rate → risk → gate → sizer → executor.

Never hits a real Bitbank private order API.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from bitbank_bot.engine import BotState, Engine
from bitbank_bot.execution_gate import ExecutionGate
from bitbank_bot.market_data import synthetic_candles
from bitbank_bot.orders import ExecutionEngine
from bitbank_bot.rest_client import OrderSubmitUncertain as RestUncertain
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import Signal
from tests.helpers import cfg, live_cfg
from tests.test_orders import _plan


def test_buy_reaches_executor_in_dry_run(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        enable_htf_filter=False,
        simulate_fill=True,
        ma_period=3,
        short_ma_period=3,
        long_ma_period=5,
    )
    rest = MagicMock()
    rest.create_order.side_effect = AssertionError("live order")
    engine = Engine(c, client=rest)
    state = BotState(None, RiskManager(c), 0, 0.0, paper_jpy=Decimal("100000"))
    with_patch = __import__("unittest.mock", fromlist=["patch"]).patch
    with with_patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal("BUY1", "buy", Decimal("0.03"), "forced", strategy_name="granville"),
    ):
        engine.process_candles(synthetic_candles(40), state, execute=True, persist=False)
    rest.create_order.assert_not_called()
    assert state.position is not None


def test_live_ready_does_not_post(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        enable_htf_filter=False,
        dry_run=False,
        live_trading=False,
        trading_mode="LIVE_READY",
        ma_period=3,
        short_ma_period=3,
        long_ma_period=5,
    )
    rest = MagicMock()
    rest.free_amount.side_effect = lambda asset: (
        Decimal("100000") if asset == "jpy" else Decimal("0")
    )
    rest.create_order.side_effect = AssertionError("live order")
    engine = Engine(c, client=rest)
    state = BotState(None, RiskManager(c), 0, 0.0)
    from unittest.mock import patch

    with patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal("BUY1", "buy", Decimal("0.03"), "forced"),
    ):
        engine.process_candles(synthetic_candles(40), state, execute=True, persist=False)
    rest.create_order.assert_not_called()
    assert state.position is None


def test_timeout_does_not_duplicate_when_order_found() -> None:
    client = MagicMock()
    recovered = {
        "order_id": "7",
        "side": "buy",
        "status": "UNFILLED",
        "executed_amount": "0",
        "average_price": "0",
        "start_amount": "0.001",
    }
    client.get_active_orders.side_effect = [[], [recovered]]
    client.create_order.side_effect = RestUncertain("timeout")
    client.get_trade_history.return_value = []
    client.get_order.return_value = recovered
    result = ExecutionEngine(live_cfg(), client).submit_order(
        Signal("BUY1", "buy", Decimal("0.03"), "t"), _plan()
    )
    assert result.ok
    assert result.order_id == "7"
    assert client.create_order.call_count == 1


def test_timeout_unknown_when_active_orders_fail() -> None:
    client = MagicMock()
    client.get_active_orders.side_effect = [
        [],
        RuntimeError("offline"),
    ]
    client.create_order.side_effect = RestUncertain("timeout")
    result = ExecutionEngine(live_cfg(), client).submit_order(
        Signal("BUY1", "buy", Decimal("0.03"), "t"), _plan()
    )
    assert not result.ok
    assert result.reason == "unknown_order_status"
    assert client.create_order.call_count == 1


def test_faults_block_orders() -> None:
    gate = ExecutionGate()
    c = live_cfg()
    signal = Signal("BUY1", "buy", Decimal("0.03"), "t")
    common = dict(
        cfg=c,
        signal=signal,
        private_api_ok=True,
        balance_ok=True,
        risk_ok=True,
        risk_reason="ok",
        kill_switch=False,
        amount=Decimal("0.001"),
        price=Decimal("10000000"),
        duplicate=False,
        open_order_conflict=False,
        atr_ok=True,
        connection_ok=True,
        recon_ok=True,
        quarantined=False,
        unknown_order=False,
        market_data_real=True,
        market_data_fresh=True,
    )
    assert gate.evaluate(**{**common, "price": Decimal("0")}).reason == "invalid_price"
    assert gate.evaluate(**{**common, "market_data_fresh": False}).reason == "stale_market_data"
    assert gate.evaluate(**{**common, "atr_ok": False}).reason == "abnormal_atr"
    assert gate.evaluate(**{**common, "connection_ok": False}).reason == "api_disconnect"
