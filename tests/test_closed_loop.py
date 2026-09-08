from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from bitbank_bot.amounts import plan_buy
from bitbank_bot.engine import Engine
from bitbank_bot.execution_gate import evaluate_gate
from bitbank_bot.indicators import atr, is_indicator_sane, rsi
from bitbank_bot.market_data import synthetic_candles
from bitbank_bot.money import D
from bitbank_bot.orders import OrderExecutor
from bitbank_bot.rate_engine import RateEngine, RateMode
from bitbank_bot.rest_client import BitbankAPIError
from bitbank_bot.strategy import Signal, Strategy, build_snapshots
from bitbank_bot.trade_signal_executor import SignalCandidate, detect_cross
from tests.helpers import cfg, risk
from tests.test_engine import FakeRest
from tests.test_orders import _plan


def test_latest_empty_keeps_real_cache(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        dry_run=True,
    )
    engine = Engine(c, client=FakeRest())  # type: ignore[arg-type]
    cached = synthetic_candles(40)
    engine.cache.merge(cached)
    rest = MagicMock()
    rest.get_candlestick.return_value = []
    incoming = engine._candles_for_cycle(rest, latest_only=True, force_synthetic=False)
    assert incoming == []
    assert engine.used_synthetic_fallback is False
    assert engine.market_data_real is True
    assert len(engine.cache.candles) == 40


def test_live_ready_logs_would_submit_without_create_order() -> None:
    client = MagicMock()
    client.create_order.side_effect = AssertionError("live order")
    c = cfg(dry_run=False, live_trading=False, trading_mode="live_ready", live_confirm=False)
    result = OrderExecutor(c, client).place(
        Signal("BUY1", "buy", Decimal("0.03"), "test"), _plan()
    )
    assert result.reason == "would_submit"
    assert result.executed_amount == Decimal("0")
    client.create_order.assert_not_called()


def test_rate_engine_fixed_keeps_buy1_tp() -> None:
    c = cfg(rate_mode="fixed", ma_period=3, short_ma_period=3, long_ma_period=5)
    snap = build_snapshots([D(100)] * 12, list(range(12)), c)[-1]
    signal = Signal("BUY1", "buy", c.buy1_tp, "MA left downtrend")
    decision = RateEngine(c).decide(signal, snap)
    assert decision.mode == RateMode.FIXED
    assert decision.take_profit_pct == c.buy1_tp
    assert decision.valid


def test_dynamic_clamps_and_rejects_bad_atr() -> None:
    c = cfg(
        rate_mode="dynamic",
        min_tp_pct=D("0.01"),
        max_tp_pct=D("0.12"),
        ma_period=3,
        short_ma_period=3,
        long_ma_period=5,
        atr_period=5,
        adx_period=5,
    )
    closes = [D(100 + i) for i in range(40)]
    snap = build_snapshots(closes, list(range(40)), c)[-1]
    signal = Signal("BUY1", "buy", c.buy1_tp, "x")
    decision = RateEngine(c).decide(signal, snap)
    assert decision.take_profit_pct >= c.min_tp_pct
    assert decision.take_profit_pct <= c.max_tp_pct
    snap.atr = D("0")
    snap.atr_pct = D("0")
    bad = RateEngine(c).decide(signal, snap)
    assert bad.valid is False
    assert "atr" in bad.reason


def test_buy_gate_reason_on_hold() -> None:
    c = cfg(ma_period=3, short_ma_period=3, long_ma_period=5)
    closes = [D(100)] * 12
    snaps = build_snapshots(closes, list(range(12)), c)
    sig = Strategy(c).evaluate(snaps[-1], None)
    assert sig.kind == "HOLD"
    assert sig.reason == "no_buy_setup"
    assert sig.gates is not None
    assert sig.score_max >= 1


def test_execution_gate_blocks_synthetic_live() -> None:
    c = cfg(dry_run=False, live_trading=True, api_key="k", api_secret="s")
    signal = Signal("BUY1", "buy", D("0.03"), "forced")
    gate = evaluate_gate(
        cfg=c,
        signal=signal,
        market_data_real=False,
        market_data_fresh=True,
        private_api_ok=True,
        balance_ok=True,
        amount=D("0.001"),
        kill_switch=False,
        duplicate_order=False,
        cooldown=False,
        open_order_conflict=False,
        connection_ok=True,
        explicit_synthetic=False,
    )
    assert not gate.allowed
    assert gate.reason in {"market_data_real", "not_synthetic_live"}


def test_detect_cross_up() -> None:
    events = detect_cross(D("99"), D("101"), D("100"))
    assert events and events[0].kind == "cross_up"


def test_signal_candidate_from_hold() -> None:
    c = cfg(ma_period=3, short_ma_period=3, long_ma_period=5)
    snap = build_snapshots([D(100)] * 12, list(range(12)), c)[-1]
    cand = SignalCandidate.from_signal(Signal.hold("no_buy_setup"), snap)
    assert cand.side == "HOLD"


def test_atr_and_rsi_defined() -> None:
    closes = [D(100 + (i % 3)) for i in range(30)]
    highs = [c + D("1") for c in closes]
    lows = [c - D("1") for c in closes]
    series = atr(highs, lows, closes, 5)
    assert any(v is not None and is_indicator_sane(v) for v in series)
    r = rsi(closes, 5)
    assert r[-1] is not None


def test_risk_based_buy_smaller_than_full_balance() -> None:
    c = cfg()
    full = plan_buy(
        available_jpy=Decimal("100000"),
        available_btc=Decimal("0"),
        price=Decimal("10000000"),
        cfg=c,
        risk=risk(c),
    )
    sized = plan_buy(
        available_jpy=Decimal("100000"),
        available_btc=Decimal("0"),
        price=Decimal("10000000"),
        cfg=c,
        risk=risk(c),
        risk_pct=Decimal("0.005"),
        stop_loss_pct=Decimal("0.02"),
    )
    assert sized.ok
    assert sized.amount < full.amount


def test_post_order_does_not_retry(monkeypatch) -> None:
    from bitbank_bot.rest_client import RestClient

    client = RestClient("https://public.example", "https://private.example", "k", "s", max_retries=5)
    calls = {"n": 0}

    def boom(*_a: object, **_k: object) -> object:
        calls["n"] += 1
        raise BitbankAPIError("timeout", unknown_submit=True)

    monkeypatch.setattr(client, "private_post", boom)
    try:
        try:
            client.create_order(
                "btc_jpy", "0.001", "buy", "limit", "1000000", live_confirmed=True
            )
        except BitbankAPIError:
            pass
        assert calls["n"] == 1
    finally:
        client.close()


def test_unknown_submit_recovers_open_order() -> None:
    client = MagicMock()
    calls = {"n": 0}

    def active(_pair: str) -> list[dict[str, str]]:
        calls["n"] += 1
        if calls["n"] == 1:
            return []
        return [
            {
                "order_id": "77",
                "identifier": "match-me",
                "side": "buy",
                "start_amount": "0.001",
                "executed_amount": "0",
                "average_price": "0",
                "status": "UNFILLED",
            }
        ]

    client.get_active_orders.side_effect = active
    recovered = {
        "order_id": "77",
        "identifier": "match-me",
        "side": "buy",
        "start_amount": "0.001",
        "executed_amount": "0",
        "average_price": "0",
        "status": "UNFILLED",
    }
    client.create_order.side_effect = BitbankAPIError("timeout", unknown_submit=True)
    client.get_order.return_value = recovered
    c = cfg(dry_run=False, live_trading=True, api_key="k", api_secret="s")
    result = OrderExecutor(c, client).place(
        Signal("BUY1", "buy", Decimal("0.03"), "test"), _plan()
    )
    assert result.ok
    assert result.order_id == "77"
    assert result.reason == "accepted_unfilled"
