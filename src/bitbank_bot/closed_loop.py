"""Closed-loop self-review and rehearsal. Does not enable LIVE or place real orders."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from bitbank_bot.amounts import AmountPlan
from bitbank_bot.config import LIVE_CONFIRM_VALUE, Config, load_config
from bitbank_bot.engine import Engine
from bitbank_bot.exchange import BitbankAdapter
from bitbank_bot.logging_setup import setup_logging, slog
from bitbank_bot.market_data import JST, fetch_candles, synthetic_candles
from bitbank_bot.orders import OrderExecutor
from bitbank_bot.paths import repo_root
from bitbank_bot.rest_client import BitbankAPIError, RestClient
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import Signal
from bitbank_bot.trade_signal_executor import TradeSignalExecutor

ROOT = repo_root()

PROGRAM_REVIEW = {
    "removed": [],
    "added": [
        "src/bitbank_bot/exchange/bitbank_adapter.py",
        "src/bitbank_bot/managers.py",
        "src/bitbank_bot/engine_state.py",
        "src/bitbank_bot/trade_state.py",
        "src/bitbank_bot/trade_signal_executor.py",
        "src/bitbank_bot/rate_engine.py",
        "src/bitbank_bot/execution_gate.py",
        "src/bitbank_bot/reconciliation.py",
        "src/bitbank_bot/self_healing.py",
        "src/bitbank_bot/paths.py",
        "src/bitbank_bot/launch.py",
        "src/bitbank_bot/closed_loop.py",
        "closed_loop.py",
    ],
    "kept": [
        "run.py (DRY_RUN screen; never create_order)",
        "src/bitbank_bot/strategy.py (README BUY1-4 / SELL1-4)",
        "src/bitbank_bot/rest_client.py (only HMAC/HTTP layer)",
        "src/bitbank_bot/orders.py (only live create_order caller)",
        "src/bitbank_bot/main.py (bot loop; bootstraps sys.path)",
    ],
}


def _cfg(**overrides: object) -> Config:
    base = Config()
    if overrides.get("dry_run") is False and overrides.get("live_trading") is True:
        if "live_trading_confirm" not in overrides:
            base.live_trading_confirm = True
        if "trading_mode" not in overrides:
            base.trading_mode = "live"
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def _plan() -> AmountPlan:
    return AmountPlan(
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


def _public_client() -> BitbankAdapter:
    return BitbankAdapter(
        RestClient("https://public.bitbank.cc", "https://api.bitbank.cc/v1")
    )


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _ok(name: str, detail: str = "") -> dict[str, Any]:
    return {"name": name, "ok": True, "detail": detail}


def _fail(name: str, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": False, "detail": detail}


def review_source(root: Path | None = None) -> dict[str, Any]:
    base = root or ROOT
    src = base / "src" / "bitbank_bot"
    checks: list[dict[str, Any]] = []

    orders = _read(src / "orders.py")
    rest = _read(src / "rest_client.py")
    engine = _read(src / "engine.py")
    config = _read(src / "config.py")
    amounts = _read(src / "amounts.py")
    launch = _read(src / "launch.py")
    main_py = _read(src / "main.py")
    start_sh = _read(base / "start.sh")
    root_main = _read(base / "main.py")
    root_loop = _read(base / "closed_loop.py")

    if "create_order" in orders and "self.client.create_order" in orders:
        checks.append(_ok("order_path", "OrderExecutor is the only live create_order caller"))
    else:
        checks.append(_fail("order_path", "OrderExecutor no longer calls create_order"))

    if "side_effect=True" in rest and "ACCESS-TIME-WINDOW" in rest:
        checks.append(_ok("hmac_post", "HMAC + ACCESS-TIME-WINDOW; order POST is not retried"))
    else:
        checks.append(_fail("hmac_post", "rest_client HMAC / no-retry contract changed"))

    if "may_place_live_orders" in config and "YES_I_ACCEPT_REAL_MONEY_RISK" in config:
        checks.append(_ok("live_gate", "LIVE needs DRY_RUN=false + LIVE_TRADING + confirm"))
    else:
        checks.append(_fail("live_gate", "live confirmation gate missing"))

    if "BITBANK_PAIR" in config and "btc_jpy" in config and "jpy_btc" in config:
        checks.append(_ok("pair_lock", "pair locked to btc_jpy; aliases rejected"))
    else:
        checks.append(_fail("pair_lock", "pair lock missing"))

    if "BITFLYER" not in engine and "COINCHECK" not in engine and "GMO" not in engine:
        checks.append(_ok("bitbank_only_engine", "engine has no other-exchange execution"))
    else:
        checks.append(_fail("bitbank_only_engine", "engine mentions another exchange"))

    if "isinstance(orders, list)" in rest and "return list(orders)" in rest:
        checks.append(_ok("active_orders_count", "get_active_orders returns a list, not dict truthiness"))
    else:
        checks.append(_fail("active_orders_count", "get_active_orders may still use dict truthiness"))

    if "synthetic_fallback_no_orders" in engine and "latest_only" in engine:
        checks.append(_ok("no_accidental_live_on_synthetic", "synthetic fallback cannot live-order"))
    else:
        checks.append(_fail("no_accidental_live_on_synthetic", "synthetic live-order guard missing"))

    if "def plan_buy" in amounts and "def plan_sell" in amounts and "create_order" not in amounts:
        checks.append(_ok("sizer_no_orders", "amounts.py only computes quantity"))
    else:
        checks.append(_fail("sizer_no_orders", "amounts.py should not place orders"))

    if "ensure_import_path" in launch and "live_intent" in launch:
        checks.append(_ok("startup_bootstrap", "launch bootstraps imports and detects live intent"))
    else:
        checks.append(_fail("startup_bootstrap", "startup launcher missing path/live guards"))

    if "_SRC" in main_py and "sys.path" in main_py:
        checks.append(_ok("package_main_bootstrap", "src/bitbank_bot/main.py bootstraps sys.path"))
    else:
        checks.append(_fail("package_main_bootstrap", "package main cannot be launched as a file"))

    if "LIVE_TRADING" in start_sh and "run.py fallback" in start_sh:
        checks.append(_ok("start_sh_live_guard", "start.sh refuses run.py when live flags are set"))
    else:
        checks.append(_fail("start_sh_live_guard", "start.sh live-guard missing"))

    if "bitbank_bot.launch" in root_main and "live_intent" in root_main:
        checks.append(_ok("root_main_uses_launch", "repo-root main.py uses the package launcher"))
    else:
        checks.append(_fail("root_main_uses_launch", "repo-root main.py does not use launch.py"))

    if "may_place_live_orders" in root_loop and "if __name__ == \"__main__\"" in root_loop:
        checks.append(_ok("root_closed_loop_launchable", "closed_loop.py stays a launchable startup file"))
    else:
        checks.append(_fail("root_closed_loop_launchable", "root closed_loop.py is not launchable"))

    failed = [c["name"] for c in checks if not c["ok"]]
    return {"ok": not failed, "failed": failed, "checks": checks}


def _check_modes() -> dict[str, Any]:
    dry = load_config(environ={"DRY_RUN": "true"}, load_default_dotenv=False)
    ready = load_config(
        environ={
            "DRY_RUN": "false",
            "LIVE_TRADING": "true",
            "BITBANK_API_KEY": "k",
            "BITBANK_API_SECRET": "s",
        },
        load_default_dotenv=False,
    )
    live = load_config(
        environ={
            "DRY_RUN": "false",
            "LIVE_TRADING": "true",
            "LIVE_TRADING_CONFIRM": LIVE_CONFIRM_VALUE,
            "BITBANK_API_KEY": "k",
            "BITBANK_API_SECRET": "s",
        },
        load_default_dotenv=False,
    )
    ok = (
        dry.resolved_trading_mode() == "dry_run"
        and dry.may_place_live_orders is False
        and ready.resolved_trading_mode() == "live_ready"
        and ready.may_place_live_orders is False
        and live.resolved_trading_mode() == "live"
        and live.may_place_live_orders is True
    )
    return {
        "ok": ok,
        "dry_run": dry.resolved_trading_mode(),
        "live_ready": ready.resolved_trading_mode(),
        "live": live.resolved_trading_mode(),
    }


def _check_public(adapter: BitbankAdapter) -> dict[str, Any]:
    ticker = adapter.get_ticker("btc_jpy")
    today = datetime.now(JST).strftime("%Y%m%d")
    yesterday = (datetime.now(JST) - timedelta(days=1)).strftime("%Y%m%d")
    today_err = None
    today_bars = 0
    try:
        today_bars = len(adapter.get_candlestick("btc_jpy", "5min", today))
    except BitbankAPIError as exc:
        today_err = {"http_status": exc.http_status, "code": exc.code}
    y_bars = len(adapter.get_candlestick("btc_jpy", "5min", yesterday))
    depth = adapter.get_depth("btc_jpy")
    c = load_config(
        environ={"DRY_RUN": "true", "CANDLE_TYPE": "5min", "ENABLE_WEBSOCKET": "false"},
        load_default_dotenv=False,
    )
    closed = fetch_candles(adapter, c, latest_only=True)
    return {
        "ok": bool(ticker.get("last")) and y_bars > 0 and len(closed) > 0,
        "last": ticker.get("last"),
        "today": {"date": today, "bars": today_bars, "error": today_err},
        "yesterday": {"date": yesterday, "bars": y_bars},
        "depth_asks": len(depth.get("asks") or []),
        "depth_bids": len(depth.get("bids") or []),
        "latest_only_closed": len(closed),
    }


def _check_cache_not_synthetic(tmp: Path) -> dict[str, Any]:
    c = _cfg(
        state_path=str(tmp / "state.json"),
        lock_path=str(tmp / "bot.lock"),
        log_dir=str(tmp / "logs"),
        enable_websocket=False,
        dry_run=True,
    )
    rest = MagicMock()
    rest.get_candlestick.side_effect = RuntimeError("no candles")
    engine = Engine(c, client=rest)
    real = synthetic_candles(10)
    engine.cache.merge(real)
    incoming = engine._candles_for_cycle(rest, latest_only=True, force_synthetic=False)
    ok = (
        incoming == []
        and engine.used_synthetic_fallback is False
        and engine.market_data_real is True
        and bool(engine.cache.candles)
    )
    return {
        "ok": ok,
        "incoming_empty": incoming == [],
        "used_synthetic_fallback": engine.used_synthetic_fallback,
        "market_data_real": engine.market_data_real,
        "cached": len(engine.cache.candles),
    }


def _check_order_rehearsal() -> dict[str, Any]:
    ready_client = MagicMock()
    ready_client.create_order.side_effect = AssertionError("live order")
    ready_cfg = _cfg(
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
        trading_mode="live_ready",
        live_trading_confirm=False,
    )
    ready = OrderExecutor(ready_cfg, ready_client).place(
        Signal("BUY1", "buy", Decimal("0.03"), "t"), _plan()
    )
    live_client = MagicMock()
    live_client.get_active_orders.return_value = []
    live_client.create_order.return_value = {
        "order_id": "1",
        "status": "FULLY_FILLED",
        "executed_amount": "0.001",
        "average_price": "10000000",
        "start_amount": "0.001",
    }
    live_cfg = _cfg(dry_run=False, live_trading=True, api_key="k", api_secret="s")
    out = TradeSignalExecutor(live_cfg, RiskManager(live_cfg), live_client).submit(
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
    ok = (
        ready.reason == "would_submit"
        and ready_client.create_order.call_count == 0
        and out.blocked == ""
        and out.result is not None
        and out.result.order_id == "1"
        and live_client.create_order.call_count == 1
    )
    return {
        "ok": ok,
        "live_ready": ready.reason,
        "live_ready_create_order_calls": ready_client.create_order.call_count,
        "live_mocked_order_id": None if out.result is None else out.result.order_id,
        "live_mocked_create_order_calls": live_client.create_order.call_count,
    }


def _check_synthetic_once(tmp: Path) -> dict[str, Any]:
    c = _cfg(
        state_path=str(tmp / "state.json"),
        lock_path=str(tmp / "bot.lock"),
        log_dir=str(tmp / "logs"),
        enable_websocket=False,
        dry_run=True,
        enable_htf_filter=False,
    )
    rest = MagicMock()
    rest.get_ticker.return_value = {"last": "10000000"}
    rest.create_order.side_effect = AssertionError("live order")
    engine = Engine(c, client=rest)
    rc = engine.run_once(synthetic=True, skip_preflight=True)
    return {
        "ok": rc == 0 and rest.create_order.call_count == 0,
        "exit": rc,
        "signal": engine.last_signal.kind,
        "reason": engine.last_signal.reason,
        "create_order_calls": rest.create_order.call_count,
        "may_place_live_orders": c.may_place_live_orders,
    }


def verify(*, public: bool = True, root: Path | None = None) -> int:
    base = root or ROOT
    setup_logging("INFO", str(base / "logs"), console=True)
    slog("BOOT", "closed_loop verify start", pair="btc_jpy")
    env_cfg = load_config(load_default_dotenv=True)
    slog(
        "BOOT",
        "mode",
        DRY_RUN=env_cfg.dry_run,
        LIVE_TRADING=env_cfg.live_trading,
        LIVE_TRADING_CONFIRM=env_cfg.live_trading_confirm,
        TRADING_MODE=env_cfg.resolved_trading_mode(),
        RATE_MODE=env_cfg.rate_mode,
        SIGNAL_ONLY=env_cfg.signal_only,
        may_place_live_orders=env_cfg.may_place_live_orders,
    )
    report: dict[str, Any] = {
        "program": "bitbank_bot.closed_loop",
        "pair": "btc_jpy",
        "review": PROGRAM_REVIEW,
        "env_mode": env_cfg.safe_dict(),
    }
    report["modes"] = _check_modes()
    tmp = base / "data" / "closed_loop_verify"
    tmp.mkdir(parents=True, exist_ok=True)
    report["cache"] = _check_cache_not_synthetic(tmp)
    report["rehearsal"] = _check_order_rehearsal()
    report["synthetic_once"] = _check_synthetic_once(tmp)
    # Source review always reads this checkout. `root` is only for logs/tmp.
    report["source"] = review_source(repo_root())
    if public:
        adapter = _public_client()
        try:
            report["public"] = _check_public(adapter)
        except Exception as exc:
            report["public"] = {"ok": False, "error": type(exc).__name__}
        finally:
            adapter.close()
    failed = [
        name
        for name, body in report.items()
        if isinstance(body, dict) and body.get("ok") is False
    ]
    report["ok"] = not failed
    report["failed"] = failed
    slog("BOOT", "closed_loop verify done", ok=report["ok"], failed=",".join(failed))
    print(json.dumps(report, indent=2, default=str, ensure_ascii=False))
    return 0 if report["ok"] else 2


def review() -> int:
    print(json.dumps(PROGRAM_REVIEW, indent=2, ensure_ascii=False))
    return 0
