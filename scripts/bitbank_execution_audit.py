#!/usr/bin/env python3
"""Read-only Bitbank execution audit. Never places an order.

Calls public ticker plus, when keys exist, GET assets / active_orders /
trade_history. Does not call POST /user/spot/order or create_order.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from bitbank_bot.config import ConfigError, load_config
    from bitbank_bot.logging_setup import setup_logging, slog
    from bitbank_bot.rest_client import RestClient
except ModuleNotFoundError as exc:
    sys.stderr.write(
        f"Missing Python package ({exc.name}). From the repo root run:\n"
        "  python3 scripts/bitbank_execution_audit.py\n"
        "or: bash start.sh --once --synthetic --skip-lock --no-screen\n"
    )
    raise SystemExit(2) from exc


def _forbid_orders(rest: RestClient) -> None:
    def _blocked(*_args: object, **_kwargs: object) -> Any:
        raise RuntimeError("execution audit must not place orders")

    rest.create_order = _blocked  # type: ignore[method-assign]
    rest.private_post = _blocked  # type: ignore[method-assign]


def run_audit(cfg, rest: RestClient) -> int:
    _forbid_orders(rest)
    slog("AUDIT", "read-only start", pair=cfg.pair, has_keys=cfg.has_keys)
    try:
        ticker = rest.get_ticker(cfg.pair)
    except Exception as exc:
        slog("AUDIT", "public ticker failed", error=type(exc).__name__)
        return 2
    slog(
        "AUDIT",
        "ticker",
        last=ticker.get("last"),
        buy=ticker.get("buy"),
        sell=ticker.get("sell"),
    )
    if not cfg.has_keys:
        slog("AUDIT", "no API keys; public ticker only")
        return 0
    try:
        assets = rest.get_assets()
        rows = assets.get("assets") or []
        free = {
            row.get("asset"): row.get("free_amount")
            for row in rows
            if row.get("asset") in {"jpy", "btc"}
        }
        slog("AUDIT", "assets free_amount", jpy=free.get("jpy"), btc=free.get("btc"))
    except Exception as exc:
        slog("AUDIT", "assets failed", error=type(exc).__name__)
        return 2
    try:
        active = rest.get_active_orders(cfg.pair)
        slog("AUDIT", "active_orders", count=len(active))
        for row in active[:10]:
            slog(
                "AUDIT",
                "active",
                order_id=row.get("order_id"),
                side=row.get("side"),
                status=row.get("status"),
                start_amount=row.get("start_amount"),
                executed_amount=row.get("executed_amount"),
            )
    except Exception as exc:
        slog("AUDIT", "active_orders failed", error=type(exc).__name__)
        return 2
    try:
        trades = rest.get_trade_history(cfg.pair)
        slog("AUDIT", "trade_history", count=len(trades))
        for row in trades[:5]:
            slog(
                "AUDIT",
                "trade",
                trade_id=row.get("trade_id"),
                side=row.get("side"),
                amount=row.get("amount"),
                price=row.get("price"),
            )
    except Exception as exc:
        slog("AUDIT", "trade_history failed", error=type(exc).__name__)
        return 2
    slog("AUDIT", "read-only complete; create_order was not called")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Bitbank execution audit")
    parser.add_argument("--env-file", default=None)
    args = parser.parse_args(argv)
    try:
        cfg = load_config(env_file=args.env_file)
    except ConfigError as exc:
        setup_logging()
        slog("ERROR", "config failed", reason=str(exc))
        return 2
    setup_logging(cfg.log_level, cfg.log_dir, console=True)
    slog("BOOT", "execution audit", **cfg.safe_dict())
    rest = RestClient(
        public_url=cfg.public_url,
        private_url=cfg.private_url,
        api_key=cfg.api_key,
        api_secret=cfg.api_secret,
        access_time_window_ms=cfg.access_time_window_ms,
        timeout_sec=cfg.http_timeout_sec,
        max_retries=cfg.max_retries,
        query_rps=cfg.query_rps,
        update_rps=cfg.update_rps,
    )
    try:
        return run_audit(cfg, rest)
    finally:
        rest.close()


if __name__ == "__main__":
    raise SystemExit(main())
