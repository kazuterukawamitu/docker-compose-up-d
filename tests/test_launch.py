from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_launch_py_compiles() -> None:
    path = Path(__file__).resolve().parents[1] / "launch.py"
    compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_launch_once_synthetic(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["STATE_PATH"] = str(tmp_path / "state.json")
    env["LOCK_PATH"] = str(tmp_path / "bot.lock")
    env["LOG_DIR"] = str(tmp_path / "logs")
    env["DRY_RUN"] = "true"
    env["LIVE_TRADING"] = "false"
    env["ENABLE_WEBSOCKET"] = "false"
    proc = subprocess.run(
        [
            sys.executable,
            str(root / "launch.py"),
            "--once",
            "--synthetic",
            "--skip-lock",
            "--no-screen",
        ],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "Bitbank BTC/JPY 起動プログラム" in proc.stdout
    assert "entry=full_package" in proc.stdout
    assert "may_place_live_orders" in proc.stdout
    assert "run_once complete" in proc.stdout
    assert "create_order" not in proc.stdout


def test_launch_doctor() -> None:
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, str(root / "launch.py"), "--doctor"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "python_executable" in proc.stdout
    assert "has_bot_package" in proc.stdout
    assert "BITBANK_API_SECRET" not in proc.stdout


def test_launch_version() -> None:
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, str(root / "launch.py"), "--version"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "bitbank-btc-jpy-bot" in proc.stdout


def test_start_sh_execs_launch_py() -> None:
    text = Path(__file__).resolve().parents[1].joinpath("start.sh").read_text(encoding="utf-8")
    after_exec = text.rsplit("exec", 1)[-1]
    assert "launch.py" in after_exec
    assert "--once" not in after_exec
