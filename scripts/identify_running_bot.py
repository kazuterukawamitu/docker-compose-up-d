#!/usr/bin/env python3
"""Identify which Bitbank bot process / checkout is running (Mac or VPS).

Read-only. Does not place orders. Helps avoid mixing iterm13 backups,
worktrees, Docker copies, and the feature-branch package.

    python3 scripts/identify_running_bot.py
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEY_FILES = (
    "src/bitbank_bot/config.py",
    "src/bitbank_bot/rest_client.py",
    "src/bitbank_bot/main.py",
    "src/bitbank_bot/watchdog.py",
    "src/bitbank_bot/strategy.py",
    "run.py",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:12]


def _ps() -> str:
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "pid,etime,args"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:  # noqa: BLE001
        return f"(ps failed: {exc})"
    lines = []
    for line in out.splitlines():
        low = line.lower()
        if "bitbank" in low or "run.py" in low or "bitbank_bot" in low:
            if "identify_running_bot" in low:
                continue
            lines.append(line.rstrip())
    return "\n".join(lines) if lines else "(no matching processes)"


def main() -> int:
    print("ROOT", ROOT)
    print("CWD ", Path.cwd())
    print("PY  ", sys.executable, sys.version.split()[0])
    print("--- key files ---")
    for rel in KEY_FILES:
        path = ROOT / rel
        if path.is_file():
            print(f"OK  {rel}  sha256={_sha256(path)}")
        else:
            print(f"MISS {rel}")
    print("--- env gates (no secrets) ---")
    for key in (
        "DRY_RUN",
        "LIVE_TRADING",
        "TRADING_MODE",
        "MODE",
        "BUY4_DIP",
        "BUY3_EXTEND",
        "MAX_BALANCE_USAGE",
    ):
        val = os.environ.get(key)
        print(f"{key}={val!r}" if val is not None else f"{key}=(unset)")
    env_path = ROOT / ".env"
    print(f".env present={env_path.is_file()}")
    print("--- processes ---")
    print(_ps())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
