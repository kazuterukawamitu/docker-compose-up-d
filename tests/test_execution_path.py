from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from bitbank_bot.amounts import AmountPlan, plan_buy
from bitbank_bot.config import LIVE_CONFIRM_VALUE, load_config
from bitbank_bot.execution_gate import ExecutionGate, GateContext
from bitbank_bot.market_data import fetch_candles
from bitbank_bot.orders import OrderExecutor
from bitbank_bot.rest_client import BitbankAPIError, RestClient
from bitbank_bot.strategy import Signal
from bitbank_bot.trade_signal_executor import TradeSignalExecutor, crossed_above
from tests.helpers import cfg, risk


def test_live_without_confirm_is_live_ready() -> None:
    loaded = load_config(
        environ={
            "DRY_RUN": "false",
            "LIVE_TRADING": "true",
            "BITBANK_API_KEY": "k",
            "BITBANK_API_SECRET": "s",
        },
        load_default_dotenv=False,
    )
    assert loaded.resolved_trading_mode() == "live_ready"
    assert loaded.may_place_live_orders is False


def test_live_with_confirm_enables_orders() -> None:
    loaded = load_config(
        environ={
            "DRY_RUN": "false",
            "LIVE_TRADING": "true",
            "LIVE_TRADING_CONFIRM": LIVE_CONFIRM_VALUE,
            "BITBANK_API_KEY": "k",
            "BITBANK_API_SECRET": "s",
        },
        load_default_dotenv=False,
    )
    assert loaded.resolved_trading_mode() == "live"
    assert loaded.may_place_live_orders is True


def test_live_ready_would_submit_does_not_call_create_order() -> None:
    client = MagicMock()
    client.create_order.side_effect = AssertionError("live order")
    c = cfg(
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
        trading_mode="live_ready",
        live_trading_confirm=False,
    )
    plan = AmountPlan(
        side="buy",
        amount=Decimal("0.001"),
        price=Decimal("10000000"),
        available_jpy=Decimal("100000"),
        available_btc=Decimal("0"),
        target_jpy=Decimal("10000"),
        planned_order_jpy=Decimal("10000"),
        actual_execution_jpy=None,
        actual_balance_jpy=Decimal("100000"),
        actual_balance_btc=Decimal("0"),
        ok=True,
        reason="ok",
    )
    result = OrderExecutor(c, client).place(Signal("BUY1", "buy", Decimal("0.03"), "t"), plan)
    assert result.reason == "would_submit"
    client.create_order.assert_not_called()


def test_gate_blocks_signal_only() -> None:
    c = cfg(signal_only=True)
    gate = ExecutionGate(c)
    decision = gate.evaluate(
        GateContext(
            signal=Signal("BUY1", "buy", Decimal("0.03"), "t"),
            market_data_real=True,
            market_data_fresh=True,
            private_api_ok=True,
            balance_ok=True,
            amount_ok=True,
            amount=Decimal("0.001"),
            kill_switch=False,
            pending_order=False,
            cooldown_active=False,
            open_order_conflict=False,
            ws_stale=False,
            explicit_synthetic=False,
        )
    )
    assert decision.allowed is False
    assert decision.reason == "signal_only_off"


def test_dynamic_size_uses_stop() -> None:
    from bitbank_bot.rate_engine import RateDecision

    c = cfg()
    rate = RateDecision(
        mode="dynamic",
        requested_mode="dynamic",
        take_profit_pct=Decimal("0.04"),
        stop_loss_pct=Decimal("0.02"),
        risk_pct=Decimal("0.01"),
        reason="test",
        market_regime="TREND",
        ok=True,
    )
    plan = plan_buy(
        available_jpy=Decimal("100000"),
        available_btc=Decimal("0"),
        price=Decimal("10000000"),
        cfg=c,
        risk=risk(c),
        rate=rate,
    )
    assert plan.ok
    assert plan.amount > 0
    assert plan.planned_order_jpy <= Decimal("100000")


def test_crossed_above() -> None:
    assert crossed_above(Decimal("99"), Decimal("101"), Decimal("100"))
    assert not crossed_above(Decimal("101"), Decimal("102"), Decimal("100"))


def test_create_order_post_is_not_retried() -> None:
    import httpx

    calls = {"n": 0}

    class FakeHttp:
        def request(self, method, url, headers=None, content=None):
            calls["n"] += 1
            raise httpx.TimeoutException("timeout")

        def close(self) -> None:
            return None

    client = RestClient(
        "https://public.example",
        "https://private.example",
        "k",
        "s",
        http=FakeHttp(),  # type: ignore[arg-type]
        max_retries=5,
    )
    try:
        raised = False
        try:
            client.create_order(
                "btc_jpy", "0.001", "buy", "limit", "10000000", live_confirmed=True
            )
        except BitbankAPIError:
            raised = True
        assert raised
        assert calls["n"] == 1
    finally:
        client.close()


def test_cached_candles_not_replaced_by_synthetic(tmp_path) -> None:
    from bitbank_bot.engine import Engine
    from bitbank_bot.market_data import synthetic_candles

    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        dry_run=True,
    )
    rest = MagicMock()
    rest.get_ticker.return_value = {"last": "10000000"}
    rest.get_candlestick.side_effect = RuntimeError("no candles")
    engine = Engine(c, client=rest)
    real = synthetic_candles(10)
    engine.cache.merge(real)
    incoming = engine._candles_for_cycle(rest, latest_only=True, force_synthetic=False)
    assert incoming == []
    assert engine.used_synthetic_fallback is False
    assert engine.market_data_real is True
    assert engine.cache.candles


def test_executor_live_submits_when_gates_pass() -> None:
    c = cfg(dry_run=False, live_trading=True, api_key="k", api_secret="s")
    client = MagicMock()
    client.get_active_orders.return_value = []
    client.create_order.return_value = {
        "order_id": "1",
        "status": "FULLY_FILLED",
        "executed_amount": "0.001",
        "average_price": "10000000",
        "start_amount": "0.001",
    }
    exe = TradeSignalExecutor(c, risk(c), client)
    from bitbank_bot.market_data import synthetic_candles

    out = exe.submit(
        Signal("BUY1", "buy", Decimal("0.03"), "t"),
        price=Decimal("10000000"),
        candles=synthetic_candles(80),
        available_jpy=Decimal("100000"),
        available_btc=Decimal("0"),
        market_data_real=True,
        market_data_fresh=True,
        private_api_ok=True,
        pending_order=False,
        kill_switch=False,
        ws_stale=False,
        explicit_synthetic=False,
    )
    assert out.blocked == ""
    assert out.result is not None
    assert out.result.order_id == "1"
    client.create_order.assert_called_once()


def test_fetch_candles_logs_api_error(caplog) -> None:
    rest = MagicMock()
    rest.get_candlestick.side_effect = BitbankAPIError(
        "fail", code=10007, http_status=200, endpoint="/btc_jpy/candlestick/5min/20260101"
    )
    c = cfg(candle_type="5min", candle_lookback_days=1)
    with caplog.at_level("INFO", logger="bitbank_bot"):
        candles = fetch_candles(rest, c)
    assert candles == []
    assert "CANDLE_API_ERROR" in caplog.text or "candlestick" in caplog.text.lower()
