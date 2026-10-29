from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from bitbank_bot.dual_run import DualRun, PluginHit, scan_plugin_source
from bitbank_bot.engine import BotState, Engine
from bitbank_bot.evidence import report_flags
from bitbank_bot.indicators import Trend
from bitbank_bot.market_data import synthetic_candles
from bitbank_bot.money import D
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import MarketSnapshot, Signal
from tests.helpers import cfg


def _snap() -> MarketSnapshot:
    return MarketSnapshot(
        index=20,
        timestamp_ms=1,
        close=D(1),
        prev_close=D(1),
        ma=D(1),
        prev_ma=D(1),
        short_ma=D(1),
        prev_short_ma=D(1),
        long_ma=D(1),
        prev_long_ma=D(1),
        ma_trend=Trend.FLAT,
        prev_ma_trend=Trend.FLAT,
        crossed_up=False,
        crossed_down=False,
        golden_cross=False,
        dead_cross=False,
        cross_price=None,
    )


def test_scan_blocks_create_order_name() -> None:
    reasons = scan_plugin_source("def create_order():\n    return 1\n")
    assert "name:create_order" in reasons


def test_scan_blocks_spot_order_path() -> None:
    reasons = scan_plugin_source('URL = "/v1/user/spot/order"\n')
    assert "spot_order_path" in reasons


def test_v31_oos_not_detected_on_this_tree() -> None:
    dual = DualRun.discover()
    assert dual.v31.status == "Not Detected"
    assert dual.oos.status == "Not Detected"
    assert dual.production_name == "strategy"
    assert dual.shadow_name == "strategy_shadow"
    assert dual.shadow_has_order_authority() is False
    assert dual.oos_tuning_applied is False


def test_unsafe_v31_is_not_imported(tmp_path) -> None:
    (tmp_path / "v31.py").write_text(
        "def create_order(*a, **k):\n    return {'order_id': 'x'}\n"
        "def fire(client):\n    return client.create_order()\n",
        encoding="utf-8",
    )
    dual = DualRun.discover(tmp_path)
    assert dual.v31.status == "unsafe"
    assert dual.v31.safe is False
    assert dual.v31.module is None
    prod = dual.make_production(cfg())
    assert type(prod).__name__ == "Strategy"


def test_safe_v31_feeds_production(tmp_path) -> None:
    (tmp_path / "v31.py").write_text(
        "from bitbank_bot.strategy import Signal\n"
        "def evaluate(snap, position):\n"
        "    return Signal.hold('v31_hold')\n",
        encoding="utf-8",
    )
    dual = DualRun.discover(tmp_path)
    assert dual.v31.status == "loaded"
    assert dual.v31_wired is False
    assert dual.production_name == "strategy"
    c = cfg()
    prod = dual.make_production(c)
    assert dual.v31_wired is True
    signal = prod.evaluate(_snap(), None)
    assert signal.reason == "v31_hold"


def test_loaded_incompatible_v31_is_not_wired_yes(tmp_path) -> None:
    (tmp_path / "v31.py").write_text("PLUGIN_MARK = 'empty'\n", encoding="utf-8")
    dual = DualRun.discover(tmp_path)
    assert dual.v31.status == "loaded"
    assert dual.production_name == "strategy"
    flags = report_flags(cfg(), dual=dual)
    assert dual.v31_wired is False
    assert flags["flags"]["v31_module"]["status"] == "PARTIAL"
    assert "not wired" in flags["flags"]["v31_module"]["evidence"]
    assert flags["flags"]["v31_module"]["status"] != "YES"


def test_plugin_strategy_without_observe_does_not_crash(tmp_path) -> None:
    (tmp_path / "v31.py").write_text(
        "from bitbank_bot.strategy import Signal\n"
        "class Strategy:\n"
        "    def __init__(self, cfg=None):\n"
        "        pass\n"
        "    def evaluate(self, snap, position):\n"
        "        return Signal.hold('v31_no_observe')\n",
        encoding="utf-8",
    )
    dual = DualRun.discover(tmp_path)
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        enable_htf_filter=False,
        dry_run=True,
        live_trading=False,
    )
    engine = Engine(c, client=None, dual=dual)
    state = BotState(None, RiskManager(c), 0, 0.0)
    signal = engine.process_candles(
        synthetic_candles(80), state, execute=False, persist=False
    )
    assert signal.reason == "v31_no_observe"
    assert dual.v31_wired is True


def test_reexported_strategy_does_not_shadow_evaluate(tmp_path) -> None:
    (tmp_path / "v31.py").write_text(
        "from bitbank_bot.strategy import Strategy, Signal\n"
        "def evaluate(snap, position):\n"
        "    return Signal.hold('plugin_evaluate')\n",
        encoding="utf-8",
    )
    dual = DualRun.discover(tmp_path)
    prod = dual.make_production(cfg())
    assert dual.v31_wired is True
    assert type(prod).__name__ == "CallableEvaluator"
    assert prod.evaluate(_snap(), None).reason == "plugin_evaluate"


class _AlwaysBuy:
    def observe(self, snap) -> None:
        return None

    def evaluate(self, snap, position) -> Signal:
        return Signal("OOS_BUY", "buy", Decimal("0.03"), "oos_only")


def test_oos_buy_never_reaches_executor(tmp_path) -> None:
    from bitbank_bot.orders import OrderExecutor

    dual = DualRun(
        v31=PluginHit("v31", None, "Not Detected", True),
        oos=PluginHit("oos", None, "Not Detected", True),
    )
    dual.make_shadow = lambda _cfg: _AlwaysBuy()  # type: ignore[method-assign]
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        enable_htf_filter=False,
        dry_run=True,
        live_trading=False,
    )
    engine = Engine(c, client=None, dual=dual)
    state = BotState(
        None,
        RiskManager(c),
        0,
        0.0,
        paper_jpy=c.dry_run_free_jpy,
        paper_btc=c.dry_run_free_btc,
    )
    real_place = OrderExecutor.place

    def wrapped(self, signal, plan):
        assert signal.kind != "OOS_BUY"
        assert signal.reason != "oos_only"
        return real_place(self, signal, plan)

    with patch("bitbank_bot.engine.OrderExecutor.place", wrapped):
        engine.process_candles(
            synthetic_candles(80), state, execute=True, persist=False
        )
    assert engine.oos_evaluations >= 1
    assert dual.last_shadow is not None
    assert dual.last_shadow.kind == "OOS_BUY"
    assert dual.shadow_has_order_authority() is False
