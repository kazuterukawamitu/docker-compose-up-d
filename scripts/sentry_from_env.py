#!/usr/bin/env python3
"""Initialize optional Sentry from SENTRY_DSN (never paste import into zsh).

Usage:
  export SENTRY_DSN='https://…@….ingest.sentry.io/…'
  python3 scripts/sentry_from_env.py

Or one line (zsh-safe):
  SENTRY_DSN='…' python3 -c 'from bitbank_bot.sentry_setup import init_sentry; print(init_sentry())'
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bitbank_bot.sentry_setup import init_sentry  # noqa: E402


def main() -> int:
    if not (os.environ.get("SENTRY_DSN") or "").strip():
        print("SENTRY_DSN unset; Sentry off. Set it in .env or the shell, then re-run.")
        print("Do not paste Python import blocks into zsh — use this script or python3 -c.")
        return 1
    ok = init_sentry(release="bitbank-btc-jpy-bot@0.1.0")
    print("sentry_active" if ok else "sentry_inactive_missing_sdk")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
