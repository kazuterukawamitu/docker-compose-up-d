"""python3 -m bitbank_bot from the repository root."""

from __future__ import annotations

from pathlib import Path

from bitbank_bot.boot import prepare_process
from bitbank_bot.main import main

if __name__ == "__main__":
    prepare_process(Path(__file__).resolve().parent)
    raise SystemExit(main())
