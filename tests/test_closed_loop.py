from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from bitbank_bot.config import LIVE_CONFIRM_PHRASE, ConfigError, load_config
from bitbank_bot.engine import BotState, Engine
from bitbank_bot.execution_gate import GateContext, evaluate_gate
from bitbank_bot.indicators import adx, atr, realized_vol
from bitbank_bot.market_data import Candle, CandleCache, fetch_candles, synthetic_candles
from bitbank_bot.money import D
from bitbank_bot.orders import OrderExecutor
from bitbank_bot.rate_engine import RateEngine
from bitbank_bot.reconciliation import ReconciliationManager
from bitbank_bot.rest_client import BitbankAPIError, RestClient
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import Signal, Strategy
from bitbank_bot.trade_signal_executor import SignalAggregator, SignalCandidate, detect_cross
from tests.helpers import cfg


def test_live_without_confirm_is_live_ready() -> None:
    loaded = load_config(
        environ={
            "DRY_RUN": "false",
            "LIVE_TRADING": "true",
            "BITBANK_API_KEY": "k",
            "BITBANK_API_SECRET": "s" * 16,
        },
        load_default_dotenv=False,
    )
    assert loaded.live_ready is True
    assert loaded.may_place_live_orders is False
    assert loaded.trading_mode == "live_ready"


def test_live_requires_confirm_phrase() -> None:
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
    assert loaded.live_ready is False
    assert loaded.may_place_live_orders is True
    assert loaded.trading_mode == "live"


def test_trading_mode_live_ready_env() -> None:
    loaded = load_config(
        environ={
            "TRADING_MODE": "live_ready",
            "BITBANK_API_KEY": "k",
            "BITBANK_API_SECRET": "s" * 16,
        },
        load_default_dotenv=False,
    )
    assert loaded.trading_mode == "live_ready"
    assert loaded.may_place_live_orders is False


def test_rate_mode_rejects_unknown() -> None:
    with pytest.raises(ConfigError, match="RATE_MODE"):
        load_config(environ={"RATE_MODE": "chaos"}, load_default_dotenv=False)


def test_atr_and_adx_on_synthetic() -> None:
    candles = synthetic_candles(80)
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    atr_s = atr(highs, lows, closes, 14)
    adx_s = adx(highs, lows, closes, 14)
    assert any(v is not None for v in atr_s)
    assert realized_vol(closes, 20) is not None
    # Synthetic series is a straight line; ADX may be low but must not crash.
    assert len(adx_s) == len(candles)


def test_rate_engine_fixed_keeps_buy1_tp() -> None:
    c = cfg()
    decision = RateEngine(c).decide(Signal("BUY1", "buy", D("0.03"), "t"), synthetic_candles(80))
    assert decision.ok
    assert decision.mode == "FIXED"
    assert decision.take_profit_pct == D("0.03")


def test_rate_engine_dynamic_clamps() -> None:
    c = cfg(rate_mode="dynamic", min_tp_pct=D("0.01"), max_tp_pct=D("0.12"))
    decision = RateEngine(c).decide(Signal("BUY1", "buy", D("0.03"), "t"), synthetic_candles(80))
    assert decision.ok
    assert decision.mode == "DYNAMIC"
    assert c.min_tp_pct <= decision.take_profit_pct <= c.max_tp_pct
    assert c.min_sl_pct <= decision.stop_loss_pct <= c.max_sl_pct
    assert c.min_risk_pct <= decision.risk_pct <= c.max_risk_pct


def test_gate_blocks_synthetic() -> None:
    c = cfg(dry_run=False, live_trading=True, live_ready=False, api_key="k", api_secret="s")
    ctx = GateContext(
        market_data_real=False,
        market_data_fresh=True,
        private_api_ok=True,
        balance_ok=True,
        kill_switch=False,
        amount=D("0.001"),
        duplicate_order=False,
        open_order_conflict=False,
        synthetic=True,
    )
    from bitbank_bot.rate_engine import RateDecision

    rate = RateDecision("FIXED", D("0.03"), D("0.02"), D("0.01"), "ok", "NORMAL", D("1"), True, None, None)
    result = evaluate_gate(c, Signal("BUY1", "buy", D("0.03"), "t"), rate, ctx)
    assert result.proceed is False
    assert result.reason in {"synthetic_market_data", "not_synthetic"}


def test_live_ready_would_submit_not_create_order() -> None:
    client = MagicMock()
    client.create_order.side_effect = AssertionError("live order")
    c = cfg(dry_run=False, live_trading=True, live_ready=True, api_key="k", api_secret="s")
    from bitbank_bot.amounts import AmountPlan

    plan = AmountPlan(
        side="buy",
        amount=D("0.001"),
        price=D("10000000"),
        available_jpy=D("100000"),
        available_btc=D("0"),
        target_jpy=D("10000"),
        planned_order_jpy=D("10000"),
        actual_execution_jpy=None,
        actual_balance_jpy=D("100000"),
        actual_balance_btc=D("0"),
        ok=True,
        reason="ok",
    )
    result = OrderExecutor(c, client).place(Signal("BUY1", "buy", D("0.03"), "t"), plan)
    assert result.reason == "would_submit"
    client.create_order.assert_not_called()


def test_cache_survives_failed_latest_fetch(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        dry_run=True,
        live_trading=False,
        poll_sec=0.01,
    )
    engine = Engine(c, client=MagicMock())
    real = synthetic_candles(40)
    engine.cache.merge(real)
    engine.market_data_real = True
    rest = MagicMock()
    rest.get_candlestick.side_effect = BitbankAPIError("boom", http_status=500, code=10000)
    incoming = engine._candles_for_cycle(rest, latest_only=True, force_synthetic=False)
    assert incoming == []
    assert engine.used_synthetic_fallback is False
    assert engine.market_data_real is True
    assert len(engine.cache.candles) == 40


def test_fetch_candles_logs_bitbank_error(monkeypatch) -> None:
    logged: list[tuple[str, str]] = []

    def fake_slog(stage: str, message: str, **fields: object) -> None:
        logged.append((stage, message))

    monkeypatch.setattr("bitbank_bot.market_data.slog", fake_slog)
    client = MagicMock()
    client.get_candlestick.side_effect = BitbankAPIError("x", code=10000, http_status=400, body={"data": {"code": 10000}})
    candles = fetch_candles(client, cfg(candle_lookback_days=1), latest_only=True)
    assert candles == []
    assert any(stage == "CANDLE_API_ERROR" for stage, _ in logged)


def test_reconcile_empty_orders_is_not_active() -> None:
    client = MagicMock()
    client.free_amount.side_effect = lambda asset: D("1") if asset == "btc" else D("1000")
    client.get_active_orders.return_value = {"orders": []}
    report = ReconciliationManager(cfg(api_key="k", api_secret="s"), client).reconcile(
        bot_btc=D("1"), pending_order_id=None, allow_paper=False
    )
    assert report.ok
    assert report.exchange_orders == 0


def test_detect_cross_and_conflict() -> None:
    assert detect_cross(D("10"), D("12"), D("11")) == "cross_up"
    assert detect_cross(D("12"), D("10"), D("11")) == "cross_down"
    chosen = SignalAggregator().choose(
        [
            SignalCandidate("BUY", D("1"), D("1"), "a", 0.2, "x", "BUY1", D("0.03")),
            SignalCandidate("SELL", D("1"), D("1"), "b", 0.9, "y", "SELL1", None),
        ]
    )
    assert chosen is not None
    assert chosen.side == "SELL"


def test_buy_gate_does_not_force_orders() -> None:
    c = cfg(ma_period=3, short_ma_period=3, long_ma_period=5)
    closes = [D("100")] * 12
    from bitbank_bot.strategy import build_snapshots

    snaps = build_snapshots(closes, list(range(len(closes))), c)
    sig = Strategy(c).evaluate(snaps[-1], None)
    assert sig.kind == "HOLD"
    assert sig.reason == "no_buy_setup"


def test_private_post_does_not_retry(monkeypatch) -> None:
    client = RestClient("https://public.example", "https://private.example", "k", "s", max_retries=5)
    calls = {"n": 0}

    class Boom:
        def request(self, *args: object, **kwargs: object) -> object:
            calls["n"] += 1
            raise __import__("httpx").ConnectError("nope")

    client.http = Boom()  # type: ignore[assignment]
    client._owns_http = False
    with pytest.raises(BitbankAPIError):
        client.private_post("/user/spot/order", {"pair": "btc_jpy"}, retry=False)
    assert calls["n"] == 1


def test_engine_execute_uses_pipeline_without_live(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        dry_run=True,
        live_trading=False,
        enable_websocket=False,
        enable_htf_filter=False,
    )
    rest = MagicMock()
    rest.create_order.side_effect = AssertionError("live")
    engine = Engine(c, client=rest)
    state = BotState(None, RiskManager(c), 0, 0.0, paper_jpy=D("100000"), paper_btc=D("0"))
    engine.market_data_real = True
    engine.used_synthetic_fallback = False
    engine._execute(Signal("BUY1", "buy", D("0.03"), "t"), D("10000000"), 1, 1, state, synthetic_candles(40))
    rest.create_order.assert_not_called()
    assert state.position is not None
