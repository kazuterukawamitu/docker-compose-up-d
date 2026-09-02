"""CLI entry. Default is a continuous DRY_RUN loop; live orders require dual flags."""

from __future__ import annotations

import argparse
import sys

from bitbank_bot.config import ConfigError, load_config
from bitbank_bot.engine import Engine, install_signal_handlers
from bitbank_bot.instance_lock import InstanceLock, InstanceLockError
from bitbank_bot.logging_setup import setup_logging, slog
from bitbank_bot.preflight import preflight
from bitbank_bot.rest_client import RestClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bitbank-bot")
    parser.add_argument(
        "--once",
        action="store_true",
        help="one cycle then exit (smoke test only; default is a continuous loop)",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="use synthetic candles (still loops unless --once is set)",
    )
    parser.add_argument("--dry-run", action="store_true", help="force DRY_RUN=true")
    parser.add_argument("--preflight", action="store_true", help="run preflight and exit")
    parser.add_argument("--check-config", action="store_true", help="load config and exit")
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="replay README rules on synthetic candles (no orders) and exit",
    )
    parser.add_argument("--skip-lock", action="store_true", help="skip instance lock")
    parser.add_argument("--env-file", default=None, help="optional .env path")
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="stop after N loop cycles (tests/smoke; default: run forever)",
    )
    return parser


def _parser() -> argparse.ArgumentParser:
    return build_parser()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
    slog(
        "BOOT",
        "mode",
        once=bool(args.once),
        synthetic=bool(args.synthetic),
        loop=not args.once,
        dry_run=cfg.dry_run,
    )
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
    if args.backtest:
        from bitbank_bot.backtest import report_lines, run_backtest
        from bitbank_bot.market_data import synthetic_candles

        report = run_backtest(synthetic_candles(240), cfg)
        for line in report_lines(report):
            slog("BACKTEST", line)
        rest.close()
        return 0
    if args.preflight:
        result = preflight(cfg, rest, require_public=not (args.synthetic or cfg.dry_run))
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
            slog("BOOT", "another instance is running; stop it or pass --skip-lock")
            rest.close()
            return 3
    try:
        if args.once:
            return engine.run_once(synthetic=args.synthetic, skip_preflight=args.synthetic)
        install_signal_handlers(engine)
        slog("BOOT", "continuous loop (HOLD/WAIT is normal; Ctrl-C to stop)")
        return engine.run_forever(
            synthetic=args.synthetic,
            max_cycles=args.max_cycles,
        )
    except KeyboardInterrupt:
        slog("BOOT", "keyboard interrupt")
        engine.request_stop()
        return 0
    finally:
        if lock:
            lock.release()
        rest.close()


def cli() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
