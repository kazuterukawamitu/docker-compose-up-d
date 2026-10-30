#!/usr/bin/env python3
"""Healthcheck for the audit agent. Fails if LIVE is YES or secrets leaked."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPORT_DIR = Path(os.environ.get("AUDIT_REPORT_DIR") or "/tmp/bitbank-audit")
REPORT = REPORT_DIR / "report.json"
HEALTH = REPORT_DIR / "health"
MAX_AGE_SEC = float(os.environ.get("AUDIT_HEALTH_MAX_AGE") or "180")


def main() -> int:
    if not REPORT.is_file() or not HEALTH.is_file():
        return 1
    age = time.time() - REPORT.stat().st_mtime
    if age > MAX_AGE_SEC:
        return 1
    if HEALTH.read_text(encoding="utf-8").strip() != "OK":
        return 1
    try:
        payload = json.loads(REPORT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 1
    if payload.get("LIVE") == "YES":
        return 1
    if payload.get("has_secret_values"):
        return 1
    if payload.get("create_order") is True:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
