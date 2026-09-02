#!/usr/bin/env python3
"""Safe environment diagnostics. Never prints API secrets or tokens."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _run(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"error:{type(exc).__name__}"
    return (proc.stdout or proc.stderr or "").strip().splitlines()[0] if proc.stdout or proc.stderr else ""


def main() -> int:
    payload: dict[str, object] = {
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "git": shutil.which("git") is not None,
        "git_version": _run(["git", "--version"]),
        "ssh": shutil.which("ssh") is not None,
        "venv": sys.prefix != getattr(sys, "base_prefix", sys.prefix),
        "cwd": str(Path.cwd()),
        "project_root": str(ROOT),
        "has_main_py": (ROOT / "main.py").is_file(),
        "has_bot_package": (ROOT / "src" / "bitbank_bot" / "__init__.py").is_file(),
        "has_env_file": (ROOT / ".env").is_file(),
        "has_api_key": bool(os.environ.get("BITBANK_API_KEY", "").strip()),
        "has_api_secret": bool(os.environ.get("BITBANK_API_SECRET", "").strip()),
        "dry_run": os.environ.get("DRY_RUN", "true"),
    }
    try:
        import dotenv  # noqa: F401

        payload["dotenv"] = True
    except ImportError:
        payload["dotenv"] = False
    try:
        import httpx

        payload["httpx"] = True
        response = httpx.get("https://public.bitbank.cc/btc_jpy/ticker", timeout=15)
        payload["public_ticker_http"] = response.status_code
        body = response.json()
        payload["public_ticker_ok"] = body.get("success") == 1
        payload["has_last_price"] = bool((body.get("data") or {}).get("last"))
    except Exception as exc:
        payload["httpx"] = payload.get("httpx", False)
        payload["public_ticker_ok"] = False
        payload["public_error"] = type(exc).__name__
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
