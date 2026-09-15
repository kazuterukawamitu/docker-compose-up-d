#!/usr/bin/env python3
"""Repo-root launcher. Prefers the enhanced package launcher; falls back to stdlib run.py.

    cd <repo> && bash ./start.sh
    python3 main.py
    python3 run.py

All stay DRY_RUN unless dual-auth LIVE is set in .env. None of these place a
Bitbank order from defaults. Do not paste this file or pytest output into zsh.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

if not (SRC / "bitbank_bot" / "launch.py").is_file() and not (ROOT / "run.py").is_file():
    sys.stderr.write(
        "cannot start: missing src/bitbank_bot/launch.py next to main.py.\n"
        "Clone ~/docker-compose-up-d and checkout cursor/bitbank-closed-loop-f964.\n"
        "  bash ~/docker-compose-up-d/start.sh\n"
        "Never ~/.venv. Never bash /workspace/start.sh on a Mac.\n"
        "Do not point CommandLineTools python3 at test_public.py / a copy of main.py.\n"
    )
    raise SystemExit(2)


def _stdlib() -> int:
    path = ROOT / "run.py"
    spec = importlib.util.spec_from_file_location("bitbank_stdlib_run", path)
    if spec is None or spec.loader is None:
        sys.stderr.write("run.py is missing; cannot start\n")
        return 2
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return int(module.main())


def _launch() -> int:
    launch_py = SRC / "bitbank_bot" / "launch.py"
    if not launch_py.is_file():
        sys.stderr.write(
            "cannot start: missing src/bitbank_bot/launch.py next to main.py.\n"
            "Clone ~/docker-compose-up-d and checkout cursor/bitbank-closed-loop-f964.\n"
            "  bash ~/docker-compose-up-d/start.sh\n"
            "Never ~/.venv. Never bash /workspace/start.sh on a Mac.\n"
        )
        return 2
    try:
        import httpx  # noqa: F401
        from bitbank_bot.launch import main as launch_main
    except ModuleNotFoundError as exc:
        name = getattr(exc, "name", "") or ""
        text = str(exc)
        if name in {"bitbank_bot", "bitbank_bot.launch"} or "bitbank_bot" in text:
            sys.stderr.write(
                "cannot import bitbank_bot.launch (need src/bitbank_bot/launch.py).\n"
                "Clone ~/docker-compose-up-d on branch cursor/bitbank-closed-loop-f964.\n"
                "  bash ~/docker-compose-up-d/start.sh\n"
                "Never ~/.venv. Never bash /workspace/start.sh on a Mac.\n"
            )
            return 2
        sys.stderr.write("full package/deps missing; starting stdlib DRY_RUN (run.py)\n")
        return _stdlib()
    return int(launch_main())


if __name__ == "__main__":
    raise SystemExit(_launch())
