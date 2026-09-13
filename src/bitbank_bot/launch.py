"""Startup program for the Bitbank BTC/JPY bot.

Works from any cwd, with or without PYTHONPATH:

    python3 main.py
    python3 src/bitbank_bot/main.py
    python3 -m bitbank_bot
    python3 closed_loop.py
    ./start.sh

Default is a continuous DRY_RUN loop. This module never flips LIVE on.
``run.py`` is used only as a last-resort DRY_RUN screen, and never when
live flags are set — that program cannot call ``create_order``.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

from bitbank_bot.paths import ensure_import_path, find_run_py, repo_root

ensure_import_path()

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in _TRUE


def _falsey(value: str | None) -> bool:
    return str(value or "").strip().lower() in _FALSE


def read_env_file(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines. Values are never logged by this helper."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            out[key] = value
    return out


def live_intent(
    *,
    environ: dict[str, str] | None = None,
    env_file: Path | None = None,
) -> bool:
    """True when env or ``.env`` asks for live / not-DRY_RUN.

    Does not print secret values. Does not enable LIVE by itself.
    """
    merged: dict[str, str] = {}
    path = env_file if env_file is not None else repo_root() / ".env"
    merged.update(read_env_file(path))
    merged.update(os.environ if environ is None else environ)
    if _falsey(merged.get("DRY_RUN")):
        return True
    if _truthy(merged.get("LIVE_TRADING")):
        return True
    mode = str(merged.get("TRADING_MODE") or "").strip().lower()
    return mode == "live"


def refuse_run_py_fallback(reason: str) -> int:
    sys.stderr.write(
        "STARTUP refused run.py fallback: "
        f"{reason}\n"
        "run.py is a stdlib DRY_RUN 取引画面 and never calls create_order.\n"
        "Install httpx + python-dotenv, then use python3 main.py or ./start.sh.\n"
    )
    return 2


def start_stdlib_screen(argv: list[str] | None = None) -> int:
    if live_intent():
        return refuse_run_py_fallback("live flags are set")
    path = find_run_py()
    if path is None:
        sys.stderr.write("STARTUP failed: run.py is missing\n")
        return 2
    spec = importlib.util.spec_from_file_location("bitbank_stdlib_run", path)
    if spec is None or spec.loader is None:
        sys.stderr.write("STARTUP failed: cannot load run.py\n")
        return 2
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    runner = getattr(module, "main", None)
    if runner is None:
        sys.stderr.write("STARTUP failed: run.py has no main()\n")
        return 2
    sys.stderr.write("STARTUP using stdlib DRY_RUN 取引画面 (run.py); no create_order\n")
    if argv is None:
        return int(runner())
    return int(runner(argv))


def start_full_bot(argv: list[str] | None = None) -> int:
    try:
        import httpx  # noqa: F401
    except ModuleNotFoundError:
        if live_intent():
            return refuse_run_py_fallback("httpx missing and live flags are set")
        return start_stdlib_screen(argv)
    from bitbank_bot.main import main as bot_main

    return int(bot_main(argv))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bitbank-launch",
        description="Start the Bitbank BTC/JPY bot (default) or run a closed-loop review.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="closed-loop rehearsal + source review (no live orders); then exit",
    )
    parser.add_argument(
        "--verify-closed-loop",
        action="store_true",
        help="alias for --verify",
    )
    parser.add_argument("--no-public", action="store_true", help="with --verify, skip public API")
    parser.add_argument("--review", action="store_true", help="print added/removed programs and exit")
    parser.add_argument(
        "--run",
        action="store_true",
        help="launch the full bot (default when --verify/--review are omitted)",
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="stdlib DRY_RUN 取引画面 (run.py); refused when live flags are set",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    ensure_import_path()
    args, rest = build_parser().parse_known_args(argv)
    if args.review:
        from bitbank_bot.closed_loop import review

        return review()
    want_verify = bool(args.verify or args.verify_closed_loop)
    if args.no_public and not args.run and not args.ui:
        want_verify = True
    if want_verify:
        from bitbank_bot.closed_loop import verify

        return verify(public=not args.no_public)
    if args.ui:
        return start_stdlib_screen(rest)
    sys.stderr.write(
        "STARTUP Bitbank BTC/JPY bot (default DRY_RUN; Ctrl-C to stop)\n"
        "HOLD/WAIT is normal. Use --verify for a closed-loop review.\n"
    )
    return start_full_bot(rest)
