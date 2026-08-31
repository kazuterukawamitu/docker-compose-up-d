"""Read-only health checks. Never calls create_order."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bitbank_bot.config import Config, ConfigError, load_config
from bitbank_bot.logging_setup import setup_logging, slog
from bitbank_bot.preflight import preflight
from bitbank_bot.rest_client import RestClient
from bitbank_bot.watchdog import WatchInput, diagnose


def run_diagnostics(
    cfg: Config,
    client: RestClient | None = None,
    *,
    require_public: bool = False,
) -> dict[str, object]:
    slog("BOOT", "diagnostics start (no orders)", dry_run=cfg.dry_run)
    report: dict[str, object] = {
        "ok": True,
        "config": cfg.safe_dict(),
        "preflight": None,
        "watchdog": None,
        "places_orders": False,
    }
    rest = client
    if rest is None:
        rest = RestClient(
            public_url=cfg.public_url,
            private_url=cfg.private_url,
            api_key=cfg.api_key,
            api_secret=cfg.api_secret,
            access_time_window_ms=cfg.access_time_window_ms,
            timeout_sec=cfg.http_timeout_sec,
            max_retries=min(2, cfg.max_retries),
            query_rps=cfg.query_rps,
            update_rps=cfg.update_rps,
        )
    result = preflight(cfg, rest, require_public=require_public)
    report["preflight"] = {"ok": result.ok, "reason": result.reason, "checks": result.checks}
    if not result.ok and require_public:
        report["ok"] = False
    status, reason = diagnose(
        WatchInput(
            now_ms=1,
            started_ms=0,
            timeout_ms=cfg.no_trade_timeout_seconds * 1000,
            stale_ms=int(cfg.stale_ws_sec * 1000),
            last_market_data_ms=0,
            strategy_evaluations=0,
            buy_signals=0,
            sell_signals=0,
            order_attempts=0,
            last_signal_kind="n/a",
            last_signal_reason="diagnostics",
            last_error="",
            last_block_reason="",
            ws_ok=False,
        )
    )
    report["watchdog"] = {"status": status, "reason": reason}
    slog("BOOT", "diagnostics complete", ok=report["ok"], preflight=result.reason)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="diagnostics",
        description="Read-only Bitbank bot diagnostics. Never places an order.",
    )
    parser.add_argument("--env-file", default=None)
    parser.add_argument(
        "--require-public",
        action="store_true",
        help="Fail if the public ticker cannot be reached",
    )
    args = parser.parse_args(argv)
    try:
        cfg = load_config(env_file=args.env_file)
    except ConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2
    cfg.dry_run = True
    cfg.live_trading = False
    setup_logging(cfg.log_dir, cfg.log_level, secrets=[cfg.api_secret, cfg.api_key])
    Path(cfg.log_dir).mkdir(parents=True, exist_ok=True)
    report = run_diagnostics(cfg, require_public=args.require_public)
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["ok"] else 2
