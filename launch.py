#!/usr/bin/env python3
"""Enhanced Bitbank BTC/JPY launcher.

This is the program that starts the bot. Default is a continuous DRY_RUN
取引画面. Live POST /user/spot/order happens only when keys exist and live
mode is requested (see docs/MASTER_REQUIREMENTS.md).

    python3 launch.py
    python3 launch.py --check
    python3 launch.py --live-ready
    python3 launch.py --live

`start.sh` execs this file after venv setup. Stdlib fallback is run.py
(DRY_RUN only).
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

LIVE_CONFIRM_OK = "YES_I_ACCEPT_REAL_MONEY_RISK"


def _read_dotenv(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def _has_keys(file_env: dict[str, str]) -> bool:
    key = (os.environ.get("BITBANK_API_KEY") or file_env.get("BITBANK_API_KEY") or "").strip()
    secret = (
        os.environ.get("BITBANK_API_SECRET") or file_env.get("BITBANK_API_SECRET") or ""
    ).strip()
    return bool(key) and bool(secret)


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="launch.py",
        description="Start the Bitbank BTC/JPY bot (DRY_RUN unless --live + keys)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="enable live orders for this process if API keys are present",
    )
    parser.add_argument(
        "--live-ready",
        action="store_true",
        help="full live path except POST /user/spot/order (WOULD_SUBMIT_ORDER)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="alias for --check-config",
    )
    return parser


def _split_argv(argv: list[str] | None) -> tuple[argparse.Namespace, list[str]]:
    parser = build_parser()
    args, rest = parser.parse_known_args(argv)
    if args.check:
        rest = ["--check-config", *rest]
    return args, rest


def _apply_mode(args: argparse.Namespace, file_env: dict[str, str]) -> str:
    if args.live and args.live_ready:
        sys.stderr.write("choose one of --live or --live-ready\n")
        raise SystemExit(2)
    if args.live:
        if not _has_keys(file_env):
            sys.stderr.write(
                "LIVE refused: BITBANK_API_KEY / BITBANK_API_SECRET missing. "
                "Put keys in .env locally. Never paste them into chat.\n"
            )
            raise SystemExit(2)
        confirm = (
            os.environ.get("LIVE_TRADING_CONFIRM")
            or file_env.get("LIVE_TRADING_CONFIRM")
            or ""
        ).strip()
        if confirm and confirm != LIVE_CONFIRM_OK:
            sys.stderr.write(
                "LIVE_TRADING_CONFIRM is set but not YES_I_ACCEPT_REAL_MONEY_RISK; "
                "degrading to LIVE_READY (no POST /user/spot/order).\n"
            )
            os.environ["DRY_RUN"] = "true"
            os.environ["LIVE_TRADING"] = "false"
            os.environ["LIVE_READY"] = "true"
            os.environ["TRADING_MODE"] = "live_ready"
            return "live_ready"
        os.environ["DRY_RUN"] = "false"
        os.environ["LIVE_TRADING"] = "true"
        os.environ["LIVE_READY"] = "false"
        os.environ["TRADING_MODE"] = "live"
        return "live"
    if args.live_ready:
        os.environ["DRY_RUN"] = "true"
        os.environ["LIVE_TRADING"] = "false"
        os.environ["LIVE_READY"] = "true"
        os.environ["TRADING_MODE"] = "live_ready"
        return "live_ready"
    if _truthy(os.environ.get("LIVE_READY") or file_env.get("LIVE_READY")):
        return "live_ready"
    dry = os.environ.get("DRY_RUN", file_env.get("DRY_RUN", "true"))
    live = os.environ.get("LIVE_TRADING", file_env.get("LIVE_TRADING", "false"))
    if not _truthy(dry) and _truthy(live):
        return "live"
    return "dry_run"


def _banner(mode: str, has_keys: bool) -> None:
    live_orders = mode == "live" and has_keys
    print("Bitbank BTC/JPY launcher", flush=True)
    print(f"TRADING_MODE={mode}", flush=True)
    print(f"DRY_RUN={os.environ.get('DRY_RUN', '')}", flush=True)
    print(f"LIVE_TRADING={os.environ.get('LIVE_TRADING', '')}", flush=True)
    print(f"LIVE_READY={os.environ.get('LIVE_READY', '')}", flush=True)
    print(f"has_api_keys={str(has_keys).lower()}", flush=True)
    print(f"may_place_live_orders={str(live_orders).lower()}", flush=True)
    if live_orders:
        print("LIVE: BUY/SELL setups will call Bitbank create_order", flush=True)
    else:
        print("no Bitbank create_order on this process unless mode=live and keys", flush=True)


def _stdlib_dry_run(rest: list[str]) -> int:
    path = ROOT / "run.py"
    spec = importlib.util.spec_from_file_location("bitbank_stdlib_run", path)
    if spec is None or spec.loader is None:
        sys.stderr.write("run.py is missing; cannot start DRY_RUN fallback\n")
        return 2
    print("full package/deps missing; starting stdlib DRY_RUN (run.py, no orders)", flush=True)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return int(module.main(rest))


def main(argv: list[str] | None = None) -> int:
    args, rest = _split_argv(argv)
    env_file = ROOT / ".env"
    file_env = _read_dotenv(env_file)
    try:
        from dotenv import load_dotenv
    except ImportError:
        for key, val in file_env.items():
            os.environ.setdefault(key, val)
    else:
        load_dotenv(env_file, override=False)

    try:
        mode = _apply_mode(args, file_env)
    except SystemExit as exc:
        return int(exc.code or 2)

    has_keys = _has_keys(file_env)
    _banner(mode, has_keys)

    try:
        import httpx  # noqa: F401
        from bitbank_bot.main import main as package_main
    except ModuleNotFoundError:
        if mode == "live":
            sys.stderr.write(
                "LIVE needs httpx (pip install -r requirements.txt). "
                "Refusing to start a second live client.\n"
            )
            return 2
        return _stdlib_dry_run(rest)
    return int(package_main(rest))


if __name__ == "__main__":
    raise SystemExit(main())
