#!/usr/bin/env python3
"""Launchable Bitbank BTC/JPY closed-loop program.

Default is a safe verify pass (public API + in-process rehearsal). It never
enables LIVE. Continuous trading is ``--run`` and still honors .env flags.

    python3 closed_loop.py
    python3 closed_loop.py --run --once --synthetic --skip-lock --no-screen
    python3 closed_loop.py --review

Order POST happens only when DRY_RUN=false, LIVE_TRADING=true, keys, and
LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK, plus a real BUY/SELL.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bitbank_bot.amounts import AmountPlan
from bitbank_bot.config import LIVE_CONFIRM_VALUE, Config, load_config
from bitbank_bot.engine import Engine
from bitbank_bot.exchange import BitbankAdapter
from bitbank_bot.logging_setup import setup_logging, slog
from bitbank_bot.market_data import JST, fetch_candles, synthetic_candles
from bitbank_bot.orders import OrderExecutor
from bitbank_bot.rest_client import BitbankAPIError, RestClient
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import Signal
from bitbank_bot.trade_signal_executor import TradeSignalExecutor


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
        "closed_loop.py",
    ],
    "kept": [
        "run.py (DRY_RUN screen; never create_order)",
        "src/bitbank_bot/strategy.py (README BUY1-4 / SELL1-4)",
        "src/bitbank_bot/rest_client.py (only HMAC/HTTP layer)",
        "src/bitbank_bot/orders.py (only live create_order caller)",
    ],
}


def _public_client() -> BitbankAdapter:
    return BitbankAdapter(
        RestClient("https://public.bitbank.cc", "https://api.bitbank.cc/v1")
    )


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


def verify(*, public: bool = True) -> int:
    setup_logging("INFO", str(ROOT / "logs"), console=True)
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
        "program": "closed_loop.py",
        "pair": "btc_jpy",
        "review": PROGRAM_REVIEW,
        "env_mode": env_cfg.safe_dict(),
    }
    report["modes"] = _check_modes()
    tmp = ROOT / "data" / "closed_loop_verify"
    tmp.mkdir(parents=True, exist_ok=True)
    report["cache"] = _check_cache_not_synthetic(tmp)
    report["rehearsal"] = _check_order_rehearsal()
    report["synthetic_once"] = _check_synthetic_once(tmp)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="closed_loop")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="safe closed-loop checks (default when --run is omitted)",
    )
    parser.add_argument("--no-public", action="store_true", help="skip live public API")
    parser.add_argument("--review", action="store_true", help="print added/removed programs")
    parser.add_argument(
        "--run",
        action="store_true",
        help="launch the full bot (main.py); still DRY_RUN unless .env is LIVE",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args, rest = build_parser().parse_known_args(argv)
    if args.review:
        return review()
    if args.run:
        from bitbank_bot.main import main as bot_main

        return bot_main(rest)
    return verify(public=not args.no_public)


if __name__ == "__main__":
    raise SystemExit(main())
