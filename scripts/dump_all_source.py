#!/usr/bin/env python3
"""Write an analysis-only concatenation of bot sources. Not executable."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bitbank_bot.code_audit import write_dump  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    del argv
    dest = write_dump(ROOT)
    sys.stdout.write(f"wrote {dest} (analysis dump; not executable)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
