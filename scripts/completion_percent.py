#!/usr/bin/env python3
"""Print a verifiable completion percent. Does not place Bitbank orders."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bitbank_bot.code_audit import analyze_python, completion_checks  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    del argv
    spec = completion_checks(ROOT, analyze_python(ROOT))
    sys.stdout.write(json.dumps(spec, indent=2, ensure_ascii=False) + "\n")
    sys.stdout.write(
        f"completion_percent={spec['completion_percent']} "
        f"passed={spec['passed']}/{spec['scored']} "
        f"live_post={spec['live_post']}\n"
    )
    return 0 if spec["passed"] == spec["scored"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
