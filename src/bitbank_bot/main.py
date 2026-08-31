"""CLI entry. Default is DRY_RUN; live orders require dual flags."""

from __future__ import annotations

import argparse
import sys

from bitbank_bot.config import ConfigError, load_config
from bitbank_bot.engine import Engine, install_signal_handlers
from bitbank_bot.instance_lock import InstanceLock, InstanceLockError
from bitbank_bot.logging_setup import setup_logging, slog
from bitbank_bot.preflight import preflight
from bitbank_bot.rest_client import RestClient


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bitbank-bot")
    parser.add_argument("--once", action="store_true", help="one cycle then exit")
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="use synthetic candles (no public history required)",
    )
    parser.add_argument("--dry-run", action="store_true", help="force DRY_RUN=true")
    parser.add_argument("--preflight", action="store_true", help="run preflight and exit")
    parser.add_argument("--check-config", action="store_true", help="load config and exit")
    parser.add_argument("--skip-lock", action="store_true", help="skip instance lock")
    parser.add_argument("--env-file", default=None, help="optional .env path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cfg = load_config(env_file=args.env_file)
    except ConfigError as exc:
        setup_logging()
        slog("ERROR", "config failed", reason=str(exc))
        return 2
    if args.dry_run:
        cfg.dry_run = True
        cfg.live_trading = False
    setup_logging(cfg.log_level, cfg.log_dir)
    slog("BOOT", "starting", **cfg.safe_dict())
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
    if args.check_config:
        slog("BOOT", "config ok", **cfg.safe_dict())
        rest.close()
        return 0
    if args.preflight:
        result = preflight(cfg, rest, require_public=not args.synthetic)
        rest.close()
        return 0 if result.ok else 2

    engine = Engine(cfg, client=rest)
    lock: InstanceLock | None = None
    if not args.skip_lock:
        try:
            lock = InstanceLock(cfg.lock_path)
            lock.acquire()
        except InstanceLockError as exc:
            slog("ERROR", str(exc))
            rest.close()
            return 3
    try:
        if args.once or args.synthetic:
            return engine.run_once(synthetic=args.synthetic, skip_preflight=args.synthetic)
        install_signal_handlers(engine)
        return engine.run_forever()
    finally:
        if lock:
            lock.release()
        rest.close()


def cli() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
