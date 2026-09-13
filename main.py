#!/usr/bin/env python3
"""Repo-root startup. Prefers the full package; falls back to stdlib run.py.

    python3 main.py
    python3 src/bitbank_bot/main.py
    python3 closed_loop.py
    python3 run.py

Default stays DRY_RUN. Live flags never silently fall back to run.py
(run.py never calls create_order).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _peek_live() -> bool:
    """Stdlib live-intent peek so a missing package still refuses run.py."""
    true = {"1", "true", "yes", "on"}
    false = {"0", "false", "no", "off"}
    merged: dict[str, str] = {}
    env_path = ROOT / ".env"
    if env_path.is_file():
        try:
            text = env_path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            merged[key.strip()] = value.strip().strip("'").strip('"')
    merged.update({k: str(v) for k, v in __import__("os").environ.items()})
    dry = merged.get("DRY_RUN", "true").strip().lower()
    live = merged.get("LIVE_TRADING", "false").strip().lower()
    mode = merged.get("TRADING_MODE", "").strip().lower()
    return dry in false or live in true or mode == "live"


def _stdlib() -> int:
    import importlib.util

    path = ROOT / "run.py"
    spec = importlib.util.spec_from_file_location("bitbank_stdlib_run", path)
    if spec is None or spec.loader is None:
        sys.stderr.write("run.py is missing; cannot start\n")
        return 2
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return int(module.main())


def _launch() -> int:
    try:
        from bitbank_bot.launch import live_intent, main as launch_main, refuse_run_py_fallback, start_stdlib_screen
    except ModuleNotFoundError as exc:
        missing = getattr(exc, "name", "") or str(exc)
        if _peek_live():
            sys.stderr.write(
                "STARTUP refused run.py fallback: "
                f"{missing} missing and live flags are set\n"
                "run.py never calls create_order. Install the package + httpx.\n"
            )
            return 2
        sys.stderr.write(
            f"full package/deps missing ({missing}); starting stdlib DRY_RUN (run.py)\n"
        )
        return _stdlib()
    try:
        import httpx  # noqa: F401
    except ModuleNotFoundError:
        if live_intent():
            return refuse_run_py_fallback("httpx missing and live flags are set")
        return start_stdlib_screen()
    return int(launch_main())


if __name__ == "__main__":
    raise SystemExit(_launch())
