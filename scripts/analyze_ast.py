#!/usr/bin/env python3
"""Write AST / inventory reports under reports/. Does not trade."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bitbank_bot.code_audit import write_ast_reports  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    del argv
    return write_ast_reports(ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
