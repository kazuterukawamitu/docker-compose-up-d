from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _launcher() -> Path:
    return _root() / "bitbank-bot"


def test_bitbank_bot_is_executable() -> None:
    path = _launcher()
    assert path.is_file()
    mode = path.stat().st_mode
    assert mode & stat.S_IXUSR
    text = path.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash")
    assert "git fetch" not in text
    assert "git checkout" not in text
    assert "cursor/bitbank-audit-unify-f5fd" not in text
    assert "TRADING_MODE=live" not in text
    assert "LIVE_TRADING=true" not in text
    assert "LIVE_TRADING_CONFIRM=" not in text
    after_exec = text.rsplit("exec", 1)[-1]
    assert "--once" not in after_exec
    assert "main.py" in after_exec
    assert "run.py" in text


def test_bitbank_bot_help() -> None:
    proc = subprocess.run(
        [str(_launcher()), "--help"],
        cwd=str(_root()),
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    combined = proc.stdout + proc.stderr
    assert "--once" in combined
    assert "--dry-run" in combined


def test_bitbank_bot_once_synthetic_dry_run(tmp_path) -> None:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["STATE_PATH"] = str(tmp_path / "state.json")
    env["LOCK_PATH"] = str(tmp_path / "bot.lock")
    env["LOG_DIR"] = str(tmp_path / "logs")
    env["DRY_RUN"] = "true"
    env["LIVE_TRADING"] = "false"
    env["ENABLE_WEBSOCKET"] = "false"
    proc = subprocess.run(
        [
            str(_launcher()),
            "--once",
            "--synthetic",
            "--dry-run",
            "--skip-lock",
            "--no-screen",
        ],
        cwd=str(_root()),
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    combined = proc.stdout + proc.stderr
    assert "may_place_live_orders" in combined
    assert "run_once complete" in combined
    assert "starting Bitbank BTC/JPY" in combined
