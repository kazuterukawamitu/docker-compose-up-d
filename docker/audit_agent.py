#!/usr/bin/env python3
"""Docker audit/test agent: gap detection vs completion criteria.

Does not place Bitbank orders. Does not load .env. Does not print secrets.
LIVE remains forced off for this process.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ["DRY_RUN"] = "true"
os.environ["LIVE_TRADING"] = "false"

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bitbank_bot.gap_audit import run_gap_audit  # noqa: E402
from bitbank_bot.quality import run_quality  # noqa: E402

REPORT_DIR = Path(os.environ.get("AUDIT_REPORT_DIR") or "/tmp/bitbank-audit")
LOOP_SEC = float(os.environ.get("AUDIT_LOOP_SEC") or "0")


def _write(report_dir: Path, payload: dict) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "report.json"
    health_path = report_dir / "health"
    text = json.dumps(payload, indent=2, default=str)
    report_path.write_text(text + "\n", encoding="utf-8")
    ok = payload.get("LIVE") != "YES" and not payload.get("has_secret_values")
    health_path.write_text("OK\n" if ok else "FAIL\n", encoding="utf-8")


def scan_once(*, quality_rc: int | None = None) -> dict:
    if quality_rc is None:
        quality_rc = run_quality(ROOT)
    report = run_gap_audit(ROOT)
    payload = report.as_dict()
    payload["quality_rc"] = quality_rc
    payload["purpose"] = "gap_detection"
    payload["create_order"] = False
    _write(REPORT_DIR, payload)
    print(json.dumps({"quality_rc": quality_rc, "LIVE": payload.get("LIVE")}, default=str))
    return payload


def main() -> int:
    payload = scan_once()
    if LOOP_SEC > 0:
        quality_rc = int(payload.get("quality_rc") or 0)
        while True:
            time.sleep(LOOP_SEC)
            payload = scan_once(quality_rc=quality_rc)
    if payload.get("LIVE") == "YES":
        return 2
    if payload.get("has_secret_values"):
        return 2
    return int(payload.get("quality_rc") or 0)


if __name__ == "__main__":
    raise SystemExit(main())
