from __future__ import annotations

import json
import time
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

from bitbank_bot.engine import Engine, PendingOrder, load_state
from bitbank_bot.market_data import parse_ohlcv, synthetic_candles
from bitbank_bot.multi_timeframe import HtfVerdict
from bitbank_bot.preflight import preflight
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import Signal
from tests.helpers import cfg


class FakeRest:
    def __init__(self) -> None:
        self.create_order_calls = 0
        self.ticker = {"last": "10000000"}
        self.status = {
            "pair": "btc_jpy",
            "status": "TRADING",
            "min_amount": "0.0001",
            "limit_max_amount": "20",
        }

    def get_ticker(self, pair: str) -> dict[str, Any]:
        assert pair == "btc_jpy"
        return self.ticker

    def get_spot_status(self, pair: str) -> dict[str, Any]:
        return self.status

    def get_assets(self) -> dict[str, Any]:
        return {"assets": [{"asset": "jpy", "free_amount": "100000"}]}

    def get_candlestick(self, pair: str, candle_type: str, date_key: str) -> list:
        return []

    def create_order(self, *args: object, **kwargs: object) -> dict[str, Any]:
        self.create_order_calls += 1
        raise AssertionError("live order")

    def close(self) -> None:
        return None


def test_parse_ohlcv_strings() -> None:
    candle = parse_ohlcv(["100", "110", "90", "105", "1.5", 1700000000000])
    assert candle.close == Decimal("105")
    assert candle.timestamp_ms == 1700000000000


def test_parse_ohlcv_json_numbers() -> None:
    candle = parse_ohlcv([100, 110, 90, 105.0, 1.5, 1700000000000])
    assert candle.close == Decimal("105.0")
    assert candle.volume == Decimal("1.5")


def test_synthetic_enough_for_ma() -> None:
    candles = synthetic_candles(80)
    assert len(candles) == 80
    assert candles[0].timestamp_ms < candles[-1].timestamp_ms


def test_preflight_dry_run_ok() -> None:
    c = cfg()
    result = preflight(c, FakeRest(), require_public=True)  # type: ignore[arg-type]
    assert result.ok
    assert "pair=btc_jpy" in result.checks


def test_preflight_honors_exchange_min() -> None:
    c = cfg(min_amount_btc=Decimal("0.00001"))
    fake = FakeRest()
    fake.status["min_amount"] = "0.0001"
    result = preflight(c, fake, require_public=True)  # type: ignore[arg-type]
    assert result.ok
    assert c.min_amount_btc == Decimal("0.0001")


def test_engine_synthetic_once_dry_run(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        dry_run=True,
        live_trading=False,
    )
    fake = FakeRest()
    engine = Engine(c, client=fake)  # type: ignore[arg-type]
    rc = engine.run_once(synthetic=True, skip_preflight=True)
    assert rc == 0
    assert fake.create_order_calls == 0
    assert engine.strategy_evaluations >= 1


def test_engine_loop_continues_after_hold(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        dry_run=True,
        live_trading=False,
        poll_sec=0.05,
    )
    fake = FakeRest()
    engine = Engine(c, client=fake)  # type: ignore[arg-type]
    rc = engine.run_forever(synthetic=True, max_cycles=3)
    assert rc == 0
    assert engine.cycles == 3
    assert engine.strategy_evaluations >= 2
    assert engine.last_watchdog == "NORMAL WAIT"
    assert fake.create_order_calls == 0


def test_dry_run_loop_without_api_keys_when_public_fails(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        dry_run=True,
        live_trading=False,
        api_key="",
        api_secret="",
        poll_sec=0.05,
    )
    rest = MagicMock()
    rest.get_ticker.side_effect = RuntimeError("no net")
    rest.get_spot_status.side_effect = RuntimeError("no net")
    rest.get_candlestick.side_effect = RuntimeError("no net")
    rest.get_assets.side_effect = AssertionError("private should not be called")
    rest.create_order.side_effect = AssertionError("live order")
    engine = Engine(c, client=rest)
    rc = engine.run_forever(synthetic=False, max_cycles=2)
    assert rc == 0
    assert engine.cycles == 2
    assert engine.used_synthetic_fallback is True
    assert engine.last_watchdog == "FAIL"
    assert engine.cache.candles == []
    rest.create_order.assert_not_called()
    rest.get_assets.assert_not_called()


def test_preflight_dry_run_no_keys_public_fail_does_not_abort() -> None:
    c = cfg(dry_run=True, live_trading=False, api_key="", api_secret="")
    rest = MagicMock()
    rest.get_ticker.side_effect = RuntimeError("offline")
    rest.get_spot_status.side_effect = RuntimeError("offline")
    result = preflight(c, rest, require_public=False)
    assert result.ok
    assert "no_keys_public_only" in result.checks


def test_engine_catchup_evaluates_missed_closed_bars(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        dry_run=True,
        live_trading=False,
        ma_period=3,
        short_ma_period=3,
        long_ma_period=5,
    )
    engine = Engine(c, client=FakeRest())  # type: ignore[arg-type]
    candles = synthetic_candles(40)
    from bitbank_bot.engine import BotState
    from bitbank_bot.risk import RiskManager
    from bitbank_bot.strategy import build_snapshots

    snaps = build_snapshots([x.close for x in candles], [x.timestamp_ms for x in candles], c)
    assert len(snaps) >= 4
    state = BotState(None, RiskManager(c), snaps[-3].timestamp_ms, 0.0)
    engine.process_candles(candles, state, execute=False)
    assert engine.strategy_evaluations == 2
    assert state.last_candle_ts == snaps[-3].timestamp_ms


def test_engine_skips_order_when_balance_fetch_fails(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        api_key="k",
        api_secret="s",
        dry_run=True,
    )
    rest = MagicMock()
    rest.free_amount.side_effect = RuntimeError("boom")
    engine = Engine(c, client=rest)
    from bitbank_bot.strategy import Signal

    state = load_state(c.state_path, c)
    engine._execute(Signal("BUY1", "buy", Decimal("0.03"), "t"), Decimal("10000000"), 1, 1, state)
    rest.create_order.assert_not_called()
    assert engine.last_block_reason == "balance_fetch_failed"


def test_load_state_without_file_has_no_pending(tmp_path) -> None:
    c = cfg(state_path=str(tmp_path / "missing.json"))
    state = load_state(c.state_path, c)
    assert state.pending is None
    assert state.position is None


def test_engine_long_wait_after_timeout(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        no_trade_timeout_seconds=900,
    )
    engine = Engine(c, client=FakeRest())  # type: ignore[arg-type]
    from bitbank_bot.engine import BotState

    state = BotState(None, RiskManager(c), 0, time.monotonic() - 901)
    engine.strategy_evaluations = 4
    engine._set_watchdog(state, Signal.hold("no_setup"))
    assert engine.last_watchdog == "LONG_WAIT"


def test_htf_blocks_buy_without_placing(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        enable_htf_filter=True,
        dry_run=True,
        live_trading=False,
        ma_period=3,
        short_ma_period=3,
        long_ma_period=5,
    )
    fake = FakeRest()
    engine = Engine(c, client=fake)  # type: ignore[arg-type]
    from bitbank_bot.engine import BotState

    state = BotState(None, RiskManager(c), 0, time.monotonic())
    blocked = HtfVerdict(False, "htf_downtrend", "DOWN", "DOWN")
    with (
        patch("bitbank_bot.engine.evaluate_htf", return_value=blocked),
        patch(
            "bitbank_bot.strategy.Strategy.evaluate",
            return_value=Signal("BUY1", "buy", Decimal("0.03"), "forced"),
        ),
    ):
        signal = engine.process_candles(
            synthetic_candles(40), state, execute=True, persist=False
        )
    assert signal.kind == "HOLD"
    assert signal.reason == "htf_downtrend"
    assert engine.last_block_reason == "htf_downtrend"
    assert fake.create_order_calls == 0
    assert state.position is None


def test_pending_unfilled_is_persisted_and_polled(tmp_path) -> None:
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
    rest.create_order.return_value = {
        "order_id": "42",
        "status": "UNFILLED",
        "executed_amount": "0",
        "average_price": "0",
        "start_amount": "0.001",
    }
    rest.get_order.return_value = {
        "order_id": "42",
        "status": "UNFILLED",
        "executed_amount": "0",
        "average_price": "0",
        "start_amount": "0.001",
    }
    engine = Engine(c, client=rest)
    from bitbank_bot.engine import BotState

    state = BotState(None, RiskManager(c), 0, time.monotonic())
    candles = synthetic_candles(40)
    with patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal("BUY1", "buy", Decimal("0.03"), "forced"),
    ):
        engine.process_candles(candles, state, execute=True, persist=True)
    assert state.pending is not None
    assert state.pending.order_id == "42"
    assert state.position is None
    saved = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert saved["pending"]["order_id"] == "42"
    rest.create_order.assert_called_once()

    state.last_candle_ts = 0
    with patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal("BUY1", "buy", Decimal("0.03"), "forced"),
    ):
        engine.process_candles(candles, state, execute=True, persist=True)
    assert engine.last_block_reason == "pending_order"
    assert rest.create_order.call_count == 1

    rest.get_order.return_value = {
        "order_id": "42",
        "status": "FULLY_FILLED",
        "executed_amount": "0.001",
        "average_price": "10000000",
        "start_amount": "0.001",
    }
    engine.process_candles(candles, state, execute=True, persist=True)
    assert state.pending is None
    assert state.position is not None
    assert state.position.actual_execution_jpy == Decimal("10000")


def test_pending_dataclass_roundtrip() -> None:
    pending = PendingOrder(
        order_id="7",
        side="buy",
        kind="BUY1",
        tp_pct=Decimal("0.03"),
        index=1,
        timestamp_ms=1,
        amount=Decimal("0.001"),
    )
    assert pending.order_id == "7"
    assert pending.filled_amount == Decimal("0")


def test_dry_run_sell_uses_position_amount(tmp_path) -> None:
    from bitbank_bot.engine import BotState
    from bitbank_bot.strategy import Position

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
    )
    engine = Engine(c, client=FakeRest())  # type: ignore[arg-type]
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
        time.monotonic(),
        paper_jpy=Decimal("90000"),
        paper_btc=Decimal("0"),
    )
    with patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal("SELL1", "sell", None, "forced"),
    ):
        engine.process_candles(synthetic_candles(40), state, execute=True, persist=False)
    assert state.position is None
    assert state.paper_btc == Decimal("0")
    assert state.paper_jpy > Decimal("90000")


def test_partial_fill_keeps_pending(tmp_path) -> None:
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
    rest.create_order.return_value = {
        "order_id": "99",
        "status": "PARTIALLY_FILLED",
        "executed_amount": "0.0004",
        "average_price": "10000000",
        "start_amount": "0.01",
    }
    engine = Engine(c, client=rest)
    from bitbank_bot.engine import BotState

    state = BotState(None, RiskManager(c), 0, time.monotonic())
    with patch(
        "bitbank_bot.strategy.Strategy.evaluate",
        return_value=Signal("BUY1", "buy", Decimal("0.03"), "forced"),
    ):
        engine.process_candles(synthetic_candles(40), state, execute=True, persist=True)
    assert state.pending is not None
    assert state.pending.order_id == "99"
    assert state.pending.filled_amount == Decimal("0.0004")
    assert state.position is not None
    assert state.position.amount == Decimal("0.0004")


def test_blocked_live_place_sets_visibility(tmp_path) -> None:
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
    )
    rest = MagicMock()
    rest.free_amount.side_effect = lambda asset: (
        Decimal("100000") if asset == "jpy" else Decimal("0")
    )
    rest.get_active_orders.return_value = [{"order_id": "9"}]
    engine = Engine(c, client=rest)
    state = load_state(c.state_path, c)
    engine._execute(
        Signal("BUY1", "buy", Decimal("0.03"), "t"), Decimal("10000000"), 1, 1, state
    )
    rest.create_order.assert_not_called()
    assert engine.last_block_reason == "active_orders"
    assert engine.last_order_result == "ORDER_BLOCKED"


def test_pending_poll_two_partials_accumulate(tmp_path) -> None:
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
    )
    rest = MagicMock()
    rest.free_amount.side_effect = lambda asset: (
        Decimal("100000") if asset == "jpy" else Decimal("0")
    )
    engine = Engine(c, client=rest)
    from bitbank_bot.engine import BotState

    state = BotState(
        None,
        RiskManager(c),
        0,
        time.monotonic(),
        pending=PendingOrder(
            order_id="42",
            side="buy",
            kind="BUY1",
            tp_pct=Decimal("0.03"),
            index=1,
            timestamp_ms=1,
            amount=Decimal("0.001"),
        ),
        paper_jpy=Decimal("100000"),
        paper_btc=Decimal("0"),
    )
    rest.get_order.return_value = {
        "order_id": "42",
        "status": "PARTIALLY_FILLED",
        "executed_amount": "0.0004",
        "average_price": "10000000",
        "start_amount": "0.001",
    }
    engine._poll_pending(state)
    assert state.pending is not None
    assert state.pending.filled_amount == Decimal("0.0004")
    assert state.position is not None
    assert state.position.amount == Decimal("0.0004")
    assert state.position.actual_execution_jpy == Decimal("4000")

    rest.get_order.return_value = {
        "order_id": "42",
        "status": "PARTIALLY_FILLED",
        "executed_amount": "0.0008",
        "average_price": "10000000",
        "start_amount": "0.001",
    }
    engine._poll_pending(state)
    assert state.pending is not None
    assert state.pending.filled_amount == Decimal("0.0008")
    assert state.position.amount == Decimal("0.0008")
    assert state.position.actual_execution_jpy == Decimal("8000")

    rest.get_order.return_value = {
        "order_id": "42",
        "status": "FULLY_FILLED",
        "executed_amount": "0.001",
        "average_price": "10000000",
        "start_amount": "0.001",
    }
    engine._poll_pending(state)
    assert state.pending is None
    assert state.position is not None
    assert state.position.amount == Decimal("0.001")
    assert state.position.actual_execution_jpy == Decimal("10000")
    assert engine.last_order_result == "FILL"


def test_poll_balance_failure_keeps_paper_and_logs(tmp_path, caplog) -> None:
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
    )
    rest = MagicMock()
    rest.free_amount.side_effect = RuntimeError("boom")
    rest.get_order.return_value = {
        "order_id": "42",
        "status": "FULLY_FILLED",
        "executed_amount": "0.001",
        "average_price": "10000000",
        "start_amount": "0.001",
    }
    engine = Engine(c, client=rest)
    engine.last_known_jpy = Decimal("90000")
    engine.last_known_btc = Decimal("0.002")
    from bitbank_bot.engine import BotState

    state = BotState(
        None,
        RiskManager(c),
        0,
        time.monotonic(),
        pending=PendingOrder(
            order_id="42",
            side="buy",
            kind="BUY1",
            tp_pct=Decimal("0.03"),
            index=1,
            timestamp_ms=1,
            amount=Decimal("0.001"),
        ),
        paper_jpy=Decimal("90000"),
        paper_btc=Decimal("0.002"),
    )
    with caplog.at_level("ERROR", logger="bitbank_bot"):
        engine._poll_pending(state)
    assert state.paper_jpy == Decimal("90000")
    assert state.paper_btc == Decimal("0.002")
    assert engine.last_known_jpy == Decimal("90000")
    assert engine.last_known_btc == Decimal("0.002")
    assert state.position is not None
    assert state.position.amount == Decimal("0.001")
    assert "balance fetch failed" in caplog.text


def test_rest_only_stale_ticker_blocks_execute(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        enable_htf_filter=False,
        stale_ws_sec=60,
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
    )
    rest = MagicMock()
    rest.free_amount.side_effect = lambda asset: (
        Decimal("100000") if asset == "jpy" else Decimal("0")
    )
    engine = Engine(c, client=rest)
    engine.last_ticker_mono = time.monotonic() - 120
    state = load_state(c.state_path, c)
    engine._execute(
        Signal("BUY1", "buy", Decimal("0.03"), "t"), Decimal("10000000"), 1, 1, state
    )
    rest.create_order.assert_not_called()
    rest.free_amount.assert_not_called()
    assert engine.last_block_reason == "stale_data"
    assert engine.last_order_result == "ORDER_BLOCKED"


def test_ticker_refresh_failure_is_logged(tmp_path, caplog) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
    )
    rest = MagicMock()
    rest.get_ticker.side_effect = RuntimeError("offline")
    engine = Engine(c, client=rest)
    with caplog.at_level("INFO", logger="bitbank_bot"):
        engine._refresh_public_last(rest)
    assert engine.last_error == "RuntimeError"
    assert engine.last_ticker_mono is None
    assert "ticker refresh failed" in caplog.text


def test_heartbeat_signal_only_skips_order_manager_ok(tmp_path, caplog) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
    )
    from bitbank_bot.engine import BotState

    engine = Engine(c, client=FakeRest())  # type: ignore[arg-type]
    state = BotState(None, RiskManager(c), 0, time.monotonic())
    with caplog.at_level("INFO", logger="bitbank_bot"):
        engine._heartbeat(state, Signal.hold("no_setup"), "1")
    assert "SIGNAL_ONLY" in caplog.text
    assert "ORDER MANAGER OK" not in caplog.text


def test_heartbeat_logs_order_manager_ok_after_simulated_fill(tmp_path, caplog) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
    )
    from bitbank_bot.engine import BotState

    engine = Engine(c, client=FakeRest())  # type: ignore[arg-type]
    engine.last_order_result = "SIMULATED_FILL"
    state = BotState(None, RiskManager(c), 0, time.monotonic())
    with caplog.at_level("INFO", logger="bitbank_bot"):
        engine._heartbeat(state, Signal.hold("no_setup"), "1")
    assert "ORDER MANAGER OK" in caplog.text
