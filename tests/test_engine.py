from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

from bitbank_bot.engine import Engine, load_state
from bitbank_bot.market_data import parse_ohlcv, synthetic_candles
from bitbank_bot.preflight import preflight
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
