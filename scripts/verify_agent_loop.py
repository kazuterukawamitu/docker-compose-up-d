#!/usr/bin/env python3
"""Docker verification agent: purpose vs package, continuously.

Runs gap_agent + bug_scan on an interval and writes JSON reports under logs/.
Read-only. Never places orders. Intended for `docker compose --profile verify`.

    python3 scripts/verify_agent_loop.py
    VERIFY_ONCE=1 python3 scripts/verify_agent_loop.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
INTERVAL = int(os.environ.get("VERIFY_INTERVAL_SEC") or "300")
ONCE = (os.environ.get("VERIFY_ONCE") or "").strip().lower() in {"1", "true", "yes", "on"}


def _run(script: str) -> dict[str, object]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    return {
        "script": script,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-1000:],
    }


def cycle() -> dict[str, object]:
    results = [_run("gap_agent.py"), _run("bug_scan.py"), _run("purpose_index.py")]
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "purpose": (
            "trading_bot: possibility/connection/operation/execution/performance success "
            "vs package; close Sakura VPS + Bitbank live gaps"
        ),
        "all_ok": all(bool(r["ok"]) for r in results),
        "results": results,
    }
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / "verify_agent.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    mark = "PASS" if payload["all_ok"] else "FAIL"
    print(f"verify_agent [{mark}] wrote {path}", flush=True)
    return payload


def main() -> int:
    while True:
        payload = cycle()
        if ONCE:
            return 0 if payload["all_ok"] else 1
        time.sleep(max(30, INTERVAL))


if __name__ == "__main__":
    raise SystemExit(main())
