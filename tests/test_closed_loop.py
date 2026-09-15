from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from bitbank_bot.config import LIVE_CONFIRM_PHRASE, load_config
from bitbank_bot.engine import BotState, Engine
from bitbank_bot.execution_gate import evaluate as gate_evaluate
from bitbank_bot.hold_tracer import root_cause
from bitbank_bot.indicators import Trend, average_true_range
from bitbank_bot.market_data import fetch_candles, synthetic_candles
from bitbank_bot.rate_engine import decide as decide_rate
from bitbank_bot.reconciliation import reconcile
from bitbank_bot.rest_client import BitbankAPIError
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import Signal
from bitbank_bot.trade_signal_executor import TradeSignalExecutor
from tests.helpers import cfg


def test_empty_latest_fetch_keeps_cached_real_candles(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        dry_run=True,
    )
    rest = MagicMock()
    rest.get_candlestick.return_value = []
    rest.get_ticker.return_value = {"last": "10000000"}
    engine = Engine(c, client=rest)
    engine.cache.merge(synthetic_candles(40))
    incoming = engine._candles_for_cycle(rest, latest_only=True, force_synthetic=False)
    assert incoming == []
    assert engine.used_synthetic_fallback is False
    assert engine.market_data_real is True
    assert len(engine.cache.candles) == 40


def test_candle_api_error_logs_bitbank_fields(caplog) -> None:
    c = cfg()
    rest = MagicMock()
    rest.get_candlestick.side_effect = BitbankAPIError(
        "api success=0 code=10000",
        code=10000,
        http_status=200,
        endpoint="/btc_jpy/candlestick/1hour/20200101",
        retry_count=0,
        body={"success": 0, "data": {"code": 10000}},
    )
    rest.public_url = "https://public.bitbank.cc"
    with caplog.at_level("INFO", logger="bitbank_bot"):
        candles = fetch_candles(rest, c, latest_only=True)
    assert candles == []
    assert "CANDLE_API_ERROR" in caplog.text
    assert "10000" in caplog.text


def test_latest_only_fetches_today_and_yesterday() -> None:
    rest = MagicMock()
    rest.get_candlestick.return_value = []
    c = cfg(candle_type="5min")
    candles = fetch_candles(rest, c, latest_only=True)
    assert candles == []
    assert rest.get_candlestick.call_count == 2
    dates = [call.args[2] for call in rest.get_candlestick.call_args_list]
    assert dates[0] != dates[1]


def test_signal_only_blocks_submit() -> None:
    loaded = load_config(
        environ={
            "DRY_RUN": "false",
            "LIVE_TRADING": "true",
            "SIGNAL_ONLY": "true",
            "LIVE_TRADING_CONFIRM": LIVE_CONFIRM_PHRASE,
            "BITBANK_API_KEY": "k",
            "BITBANK_API_SECRET": "s" * 16,
        },
        load_default_dotenv=False,
    )
    assert loaded.signal_only is True
    assert loaded.may_place_live_orders is False
    result = gate_evaluate(
        loaded,
        Signal("BUY1", "buy", Decimal("0.03"), "t"),
        market_data_real=True,
        market_data_fresh=True,
        private_api_ok=True,
        balance_ok=True,
        amount_ok=True,
        kill_switch=False,
        duplicate_order=False,
        open_order_conflict=False,
        stale_websocket=False,
    )
    assert result.allowed is False
    assert result.reason == "SIGNAL_ONLY"


def test_live_without_confirm_phrase_is_live_ready() -> None:
    loaded = load_config(
        environ={
            "DRY_RUN": "false",
            "LIVE_TRADING": "true",
            "BITBANK_API_KEY": "k",
            "BITBANK_API_SECRET": "s" * 16,
        },
        load_default_dotenv=False,
    )
    assert loaded.trading_mode == "live_ready"
    assert loaded.may_place_live_orders is False


def test_live_with_confirm_phrase_enables_orders() -> None:
    loaded = load_config(
        environ={
            "DRY_RUN": "false",
            "LIVE_TRADING": "true",
            "LIVE_TRADING_CONFIRM": LIVE_CONFIRM_PHRASE,
            "BITBANK_API_KEY": "k",
            "BITBANK_API_SECRET": "s" * 16,
        },
        load_default_dotenv=False,
    )
    assert loaded.trading_mode == "live"
    assert loaded.may_place_live_orders is True


def test_live_ready_would_submit_does_not_create_order() -> None:
    client = MagicMock()
    client.create_order.side_effect = AssertionError("live order")
    client.get_active_orders.return_value = []
    c = cfg(dry_run=False, live_trading=True, api_key="k", api_secret="s", trading_mode="live_ready")
    assert c.may_place_live_orders is False
    from bitbank_bot.amounts import AmountPlan

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
    result = TradeSignalExecutor(c, client).submit(
        Signal("BUY1", "buy", Decimal("0.03"), "t"),
        plan,
        trace_id="abc123",
        market_data_real=True,
        market_data_fresh=True,
        private_api_ok=True,
        kill_switch=False,
        duplicate_order=False,
        open_order_conflict=False,
        stale_websocket=False,
    )
    assert result.reason == "would_submit"
    client.create_order.assert_not_called()


def test_gate_blocks_synthetic_data() -> None:
    c = cfg(dry_run=False, live_trading=True, api_key="k", api_secret="s")
    result = gate_evaluate(
        c,
        Signal("BUY1", "buy", Decimal("0.03"), "t"),
        market_data_real=False,
        market_data_fresh=True,
        private_api_ok=True,
        balance_ok=True,
        amount_ok=True,
        kill_switch=False,
        duplicate_order=False,
        open_order_conflict=False,
        stale_websocket=False,
    )
    assert result.allowed is False
    assert result.reason == "synthetic_market_data"


def test_dynamic_rate_blocks_invalid_atr() -> None:
    c = cfg(rate_mode="dynamic")
    decision = decide_rate(
        c,
        Signal("BUY1", "buy", Decimal("0.03"), "t"),
        atr=None,
        price=Decimal("10000000"),
        trend=Trend.UP,
    )
    assert decision.allow_trade is False
    assert decision.reason == "atr_invalid"


def test_atr_from_ranges() -> None:
    highs = [Decimal("10"), Decimal("12"), Decimal("11")]
    lows = [Decimal("9"), Decimal("10"), Decimal("9")]
    closes = [Decimal("9.5"), Decimal("11"), Decimal("10")]
    atr = average_true_range(highs, lows, closes, 2)
    assert atr is not None
    assert atr > 0


def test_hold_tracer_no_setup() -> None:
    assert root_cause(Signal.hold("no_buy_setup")) == "NO_SETUP"
    assert (
        root_cause(Signal.hold("x"), synthetic_fallback=True) == "SYNTHETIC_DATA_BLOCK"
    )
    assert root_cause(Signal.hold("stale_market_data")) == "STALE_MARKET_DATA"


def test_reconcile_detects_untracked_open_orders() -> None:
    client = MagicMock()
    client.free_amount.side_effect = lambda asset: Decimal("1") if asset == "btc" else Decimal("1000")
    client.get_active_orders.return_value = [{"order_id": "7"}]
    report = reconcile(client, "btc_jpy", None, pending_order_id=None, min_amount=Decimal("0.0001"))
    assert report.ok is False
    assert report.reason == "untracked_open_orders"


def test_cached_real_data_still_executes_after_failed_refresh(tmp_path) -> None:
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
        poll_sec=0.01,
    )
    rest = MagicMock()
    rest.get_ticker.return_value = {"last": "10000000"}
    rest.get_spot_status.return_value = {"pair": "btc_jpy", "status": "TRADING"}
    rest.get_candlestick.side_effect = RuntimeError("boom")
    engine = Engine(c, client=rest)
    engine.cache.merge(synthetic_candles(40))
    incoming = engine._candles_for_cycle(rest, latest_only=True, force_synthetic=False)
    assert engine.used_synthetic_fallback is False
    candles = engine.cache.merge(incoming)
    from unittest.mock import patch

    state = BotState(None, RiskManager(c), 0, 0.0)
    with patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal("BUY1", "buy", Decimal("0.03"), "forced"),
    ):
        engine.process_candles(candles, state, execute=True, persist=False)
    assert state.position is not None
    assert state.position.kind == "BUY1"


def test_explicit_synthetic_once_is_not_real_data(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        dry_run=True,
        live_trading=False,
    )
    rest = MagicMock()
    rest.create_order.side_effect = AssertionError("live order")
    engine = Engine(c, client=rest)
    assert engine.run_once(synthetic=True, skip_preflight=True) == 0
    assert engine.market_data_real is False
    assert engine._explicit_synthetic is True
    rest.create_order.assert_not_called()


def test_live_explicit_synthetic_does_not_post(tmp_path) -> None:
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
        live_trading_confirm=True,
        trading_mode="live",
        ma_period=3,
        short_ma_period=3,
        long_ma_period=5,
        poll_sec=0.01,
    )
    rest = MagicMock()
    rest.get_ticker.return_value = {"last": "10000000"}
    rest.get_spot_status.return_value = {"pair": "btc_jpy", "status": "TRADING"}
    rest.get_assets.return_value = {"assets": []}
    rest.free_amount.return_value = Decimal("100000")
    rest.create_order.side_effect = AssertionError("live order")
    engine = Engine(c, client=rest)
    from unittest.mock import patch

    with patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal("BUY1", "buy", Decimal("0.03"), "forced"),
    ):
        rc = engine.run_forever(synthetic=True, max_cycles=1)
    assert rc == 0
    rest.create_order.assert_not_called()
