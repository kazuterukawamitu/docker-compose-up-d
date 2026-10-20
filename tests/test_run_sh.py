from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_run_sh_help_embeds_absolute_commands() -> None:
    text = (ROOT / "run.sh").read_text(encoding="utf-8")
    assert "filesystem root" in text
    assert "`/run.sh` is filesystem root and is wrong." in text
    mac = "/Users/kazuterukawamitsu/btc-jpy-trading-bot/iterm13/iterm15-2/iterm13/5841/run.sh"
    for name in ("help", "check", "dry", "once", "live-ready"):
        assert f"{mac} {name}" in text
    proc = subprocess.run(
        ["bash", str(ROOT / "run.sh"), "help"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert f"{ROOT / 'run.sh'} help" in proc.stdout
    assert f"{mac} dry" in proc.stdout
    assert "filesystem root" in proc.stdout


def test_run_sh_check_exits_zero(tmp_path) -> None:
    env = os.environ.copy()
    env["STATE_PATH"] = str(tmp_path / "state.json")
    env["LOCK_PATH"] = str(tmp_path / "bot.lock")
    env["LOG_DIR"] = str(tmp_path / "logs")
    env["DRY_RUN"] = "true"
    env["LIVE_TRADING"] = "false"
    proc = subprocess.run(
        ["bash", str(ROOT / "run.sh"), "check"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout


def test_run_sh_unknown_command() -> None:
    proc = subprocess.run(
        ["bash", str(ROOT / "run.sh"), "nope"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert proc.returncode == 2
