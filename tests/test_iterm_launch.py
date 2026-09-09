from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _script() -> Path:
    return _root() / "scripts" / "iterm-launch.sh"


def test_iterm_launch_is_executable_and_safe() -> None:
    path = _script()
    assert path.is_file()
    assert path.stat().st_mode & stat.S_IXUSR
    text = path.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash")
    assert "TRADING_MODE=live" not in text
    assert "LIVE_TRADING=true" not in text
    assert "LIVE_TRADING_CONFIRM=" not in text
    assert "src/bitbank_bot/__init__.py" in text
    assert "git checkout" in text
    assert 'BOT_BRANCH="cursor/closed-loop-runtime-hardening"' in text
    after_exec = text.rsplit("exec", 1)[-1]
    assert "--once" not in after_exec
    assert "bitbank-bot" in after_exec or "start.sh" in after_exec or "run.py" in after_exec


def test_readme_has_home_safe_one_liner() -> None:
    text = (_root() / "README.md").read_text(encoding="utf-8")
    assert "no such file or directory" in text
    assert "scripts/iterm-launch.sh" in text
    assert "python3 \"$HOME/iterm15\"" in text
    assert "Paste **this one line**" in text


def test_iterm_launch_from_other_cwd(tmp_path) -> None:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["STATE_PATH"] = str(tmp_path / "state.json")
    env["LOCK_PATH"] = str(tmp_path / "bot.lock")
    env["LOG_DIR"] = str(tmp_path / "logs")
    env["DRY_RUN"] = "true"
    env["LIVE_TRADING"] = "false"
    env["ENABLE_WEBSOCKET"] = "false"
    env["HOME"] = str(tmp_path / "home")
    (tmp_path / "home").mkdir()
    proc = subprocess.run(
        [
            str(_script()),
            "--once",
            "--synthetic",
            "--dry-run",
            "--skip-lock",
            "--no-screen",
        ],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    combined = proc.stdout + proc.stderr
    assert "starting from" in combined
    assert "may_place_live_orders" in combined
    assert "run_once complete" in combined
    assert "trading_mode" in combined
    assert '"trading_mode": "DRY_RUN"' in combined or "trading_mode=DRY_RUN" in combined
