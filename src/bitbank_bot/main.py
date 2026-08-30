"""CLI: python -m bitbank_bot [--once|--check-config|--backtest]."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bitbank_bot.config import ConfigError, load_config
from bitbank_bot.engine import Engine, install_signal_handlers
from bitbank_bot.instance_lock import InstanceLock, InstanceLockError
from bitbank_bot.logging_setup import setup_logging, slog
from bitbank_bot.money import D
from bitbank_bot.preflight import preflight
from bitbank_bot.rest_client import RestClient


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bitbank_bot",
        description="Bitbank BTC/JPY MA bot. Default DRY_RUN=true (no live orders).",
    )
    p.add_argument("--env-file", default=None, help="Path to .env")
    p.add_argument("--once", action="store_true", help="One evaluate cycle then exit")
    p.add_argument("--synthetic", action="store_true", help="Use dummy candles (no hang)")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Force DRY_RUN (log ORDER_INTENT only; never call create_order)",
    )
    p.add_argument("--check-config", action="store_true", help="Validate config and exit")
    p.add_argument("--preflight", action="store_true", help="Run preflight only")
    p.add_argument("--audit", action="store_true", help="Read-only fill vs Bitbank audit")
    p.add_argument("--backtest", metavar="CSV", nargs="?", const="", help="Replay CSV candles")
    p.add_argument("--dashboard", action="store_true", help="Rich status table")
    p.add_argument("--skip-lock", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cfg = load_config(env_file=args.env_file)
    except ConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2
    if args.dry_run:
        cfg.dry_run = True
        cfg.live_trading = False
    if args.dashboard:
        cfg.dashboard = True
    setup_logging(cfg.log_dir, cfg.log_level, secrets=[cfg.api_secret, cfg.api_key])
    slog("BOOT", "config loaded", **{k: str(v) for k, v in cfg.safe_dict().items()})
    slog(
        "CONFIG",
        "mode",
        dry_run=cfg.dry_run,
        live_trading=cfg.live_trading,
        may_place_live_orders=cfg.may_place_live_orders,
    )
    if args.check_config:
        print(json.dumps(cfg.safe_dict(), indent=2, default=str))
        return 0
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
    if args.preflight:
        result = preflight(cfg, rest, require_public=not args.synthetic)
        print(result.reason)
        return 0 if result.ok else 2
    if args.audit:
        from bitbank_bot.audit import run_audit

        report = run_audit(cfg, rest)
        print(json.dumps(report.as_dict(), indent=2))
        return 0 if report.consistent else 2
    if args.backtest is not None:
        from bitbank_bot.backtest import load_csv, run_backtest
        from bitbank_bot.market_data import track_record_candles

        candles = load_csv(Path(args.backtest)) if args.backtest else track_record_candles()
        report = run_backtest(candles, cfg, initial_jpy=D("1000000"))
        print(json.dumps(report.as_dict(), indent=2))
        return 0

    engine = Engine(cfg, client=rest)
    lock: InstanceLock | None = None
    if not args.skip_lock:
        try:
            lock = InstanceLock(cfg.lock_path)
            lock.acquire()
        except InstanceLockError as exc:
            slog("ERROR", str(exc))
            return 3
    try:
        if args.once or args.synthetic:
            rc = engine.run_once(synthetic=args.synthetic, skip_preflight=args.synthetic)
            if rc == 0 and args.once:
                sys.stdout.write("\a")
                sys.stdout.flush()
            return rc
        install_signal_handlers(engine)
        return engine.run_forever()
    finally:
        if lock:
            lock.release()
        rest.close()


def cli() -> None:
    raise SystemExit(main())
