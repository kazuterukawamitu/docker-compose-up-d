#!/usr/bin/env python3
"""Start the Bitbank BTC/JPY bot from the files already in this folder.

Git login, clone, fetch, and checkout are not used. If the full package
cannot be imported, this falls back to the stdlib DRY_RUN program in run.py.

Live orders stay off unless the existing config already has DRY_RUN=false,
LIVE_TRADING=true, and both API keys. This launcher does not set those flags.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _stdlib(argv: list[str] | None) -> int:
    path = ROOT / "run.py"
    if not path.is_file():
        sys.stderr.write(
            "run.py is not in this folder. This launcher does not download "
            "or log in to Git. Use the directory that already contains the bot.\n"
        )
        return 2
    spec = importlib.util.spec_from_file_location("bitbank_stdlib_run", path)
    if spec is None or spec.loader is None:
        sys.stderr.write("run.py could not be loaded\n")
        return 2
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if argv is None:
        return int(module.main())
    return int(module.main(argv))


def main(argv: list[str] | None = None) -> int:
    os.chdir(ROOT)
    sys.stdout.write(
        "Bitbank BTC/JPY launcher: local files only, no Git login. "
        "Live orders stay off unless DRY_RUN=false and LIVE_TRADING=true "
        "are already set with API keys.\n"
    )
    sys.stdout.flush()
    if not (SRC / "bitbank_bot" / "__init__.py").is_file():
        sys.stderr.write("package missing; starting stdlib DRY_RUN (run.py)\n")
        return _stdlib(argv)
    try:
        import httpx  # noqa: F401
        from bitbank_bot.main import main as bot_main
    except ModuleNotFoundError:
        sys.stderr.write("full package/deps missing; starting stdlib DRY_RUN (run.py)\n")
        return _stdlib(argv)
    return int(bot_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
