#!/usr/bin/env python3
"""Start the Bitbank BTC/JPY bot from the files next to this script.

Git login is not used. This program does not clone, fetch, or checkout.
It does not place a Bitbank order. Live trading stays at whatever
DRY_RUN / LIVE_TRADING are already set to (default: no live orders).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Steps this file runs, in order. Nothing here contacts Git.
INSTRUCTIONS = (
    "locate this script's directory",
    "require local bot files (no remote download)",
    "choose the current Python, or run.py if packages are missing",
    "show DRY_RUN and LIVE_TRADING without printing secrets",
    "start the local bot",
)

REQUIRED = (
    "main.py",
    "run.py",
    "requirements.txt",
    ".env.example",
    "src/bitbank_bot/__init__.py",
    "src/bitbank_bot/main.py",
)

_LAUNCHER_FLAGS = {"--check", "--no-venv"}
_NO_SCREEN = {
    "--once",
    "--check-config",
    "--preflight",
    "--backtest",
    "--no-screen",
    "--screen",
}


def _say(status: str, step: str, detail: str = "") -> None:
    line = f"LAUNCH {status} {step}"
    if detail:
        line = f"{line} {detail}"
    print(line, flush=True)


def _flag(name: str, default: str) -> str:
    if name in os.environ:
        return os.environ[name]
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return default
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip().strip("'\"")
    return default


def verify_local_sources() -> list[str]:
    return [rel for rel in REQUIRED if not (ROOT / rel).is_file()]


def _deps_ok() -> bool:
    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        import dotenv  # noqa: F401
        import httpx  # noqa: F401
        from bitbank_bot.main import main as _main  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True


def _forwarded(argv: list[str]) -> list[str]:
    args = [item for item in argv if item not in _LAUNCHER_FLAGS]
    if any(item in _NO_SCREEN for item in args):
        return args
    if sys.stdout.isatty():
        return ["--screen", *args]
    return args


def _run_stdlib(argv: list[str]) -> int:
    import importlib.util

    path = ROOT / "run.py"
    spec = importlib.util.spec_from_file_location("bitbank_stdlib_run", path)
    if spec is None or spec.loader is None:
        _say("FAIL", "stdlib DRY_RUN", "run.py missing")
        return 2
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return int(module.main(argv))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    check_only = "--check" in args
    os.chdir(ROOT)
    _say("PASS", "instructions", str(len(INSTRUCTIONS)))
    _say("PASS", "project_root", str(ROOT))

    missing = verify_local_sources()
    if missing:
        _say("FAIL", "local_sources", "missing=" + ",".join(missing))
        print(
            "Git login is not used. Keep the bot files beside launch.py and run again.",
            file=sys.stderr,
            flush=True,
        )
        return 2
    _say("PASS", "local_sources")
    _say("PASS", "git_login", "not_required")

    dry = _flag("DRY_RUN", "true")
    live = _flag("LIVE_TRADING", "false")
    _say("PASS", "trading_mode", f"DRY_RUN={dry} LIVE_TRADING={live}")
    print(
        "This launcher does not enable live orders and does not call Bitbank create_order.",
        flush=True,
    )

    forwarded = _forwarded(args)
    if not _deps_ok():
        _say("FAIL", "dependencies", "stdlib DRY_RUN via run.py")
        fallback = ["--once", "--synthetic", "--no-screen"] if check_only else forwarded
        return _run_stdlib(fallback)

    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    os.environ["PYTHONPATH"] = src + (
        os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else ""
    )
    os.environ["PYTHONUNBUFFERED"] = "1"

    from bitbank_bot.main import main as bot_main

    if check_only:
        code = int(bot_main(["--check-config", "--no-screen"]))
        _say("PASS" if code == 0 else "FAIL", "check_config", f"exit={code}")
        return code

    _say("PASS", "start", "main.py")
    return int(bot_main(forwarded))


if __name__ == "__main__":
    raise SystemExit(main())
