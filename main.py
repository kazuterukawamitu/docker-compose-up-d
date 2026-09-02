#!/usr/bin/env python3
"""Repo-root launcher. Prefers the full package; falls back to stdlib run.py.

    python3 main.py
    python3 run.py

Both stay DRY_RUN. Neither places a Bitbank order.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


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
    try:
        import httpx  # noqa: F401
        from bitbank_bot.main import main
    except ModuleNotFoundError:
        sys.stderr.write("full package/deps missing; starting stdlib DRY_RUN (run.py)\n")
        return _stdlib()
    return int(main())


if __name__ == "__main__":
    raise SystemExit(_launch())
