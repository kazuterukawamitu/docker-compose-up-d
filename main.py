#!/usr/bin/env python3
"""Repo-root launcher. Prefers the full package; stdlib fallback otherwise.

    python3 main.py          # DRY_RUN (run.py if httpx missing)
    python3 trade.py --live  # real orders when .env has keys
    python3 run.py           # paper screen, never orders
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _dotenv_flag(name: str, default: str = "") -> str:
    path = ROOT / ".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    import os

    return os.environ.get(name, default)


def _truthy(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _wants_live(argv: list[str]) -> bool:
    if "--require-live" in argv:
        return True
    if _truthy(_dotenv_flag("LIVE_TRADING", "false")):
        return True
    dry = _dotenv_flag("DRY_RUN", "true")
    return dry.strip().lower() in {"0", "false", "no", "off"}


def _stdlib(path: Path, argv: list[str] | None = None) -> int:
    spec = importlib.util.spec_from_file_location("bitbank_stdlib_run", path)
    if spec is None or spec.loader is None:
        sys.stderr.write(f"{path.name} is missing; cannot start\n")
        return 2
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if argv is None:
        return int(module.main())
    return int(module.main(argv))


def _launch() -> int:
    argv = sys.argv[1:]
    try:
        import httpx  # noqa: F401
        from bitbank_bot.main import main
    except ModuleNotFoundError:
        if (
            _wants_live(argv)
            and "--synthetic" not in argv
            and "--dry-run" not in argv
        ):
            if any(flag in argv for flag in ("--check-config", "--preflight", "--backtest")):
                sys.stderr.write(
                    "LIVE check needs httpx. pip install -r requirements.txt "
                    "or run: python3 trade.py --live\n"
                )
                return 2
            live_argv = list(argv)
            if "--live" not in live_argv and "--require-live" not in live_argv:
                live_argv.insert(0, "--live")
            sys.stderr.write("full package/deps missing; starting stdlib trade.py --live\n")
            return _stdlib(ROOT / "trade.py", live_argv)
        sys.stderr.write("full package/deps missing; starting stdlib DRY_RUN (run.py)\n")
        return _stdlib(ROOT / "run.py")
    return int(main())


if __name__ == "__main__":
    raise SystemExit(_launch())
