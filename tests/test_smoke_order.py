from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from bitbank_bot.config import LIVE_CONFIRM_PHRASE
from bitbank_bot.main import main
from bitbank_bot.smoke_order import run_smoke_order
from tests.helpers import cfg


def test_smoke_order_simulated_fill() -> None:
    rc = run_smoke_order(cfg())
    assert rc == 0


def test_smoke_order_refuses_live() -> None:
    c = cfg(
        dry_run=False,
        live_trading=True,
        live_trading_confirm=True,
        trading_mode="LIVE",
        api_key="k",
        api_secret="s",
    )
    assert c.may_place_live_orders
    assert run_smoke_order(c) == 2


def test_smoke_order_cli_never_posts(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("LOCK_PATH", str(tmp_path / "bot.lock"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("LIVE_TRADING", "false")
    rc = main(["--smoke-order", "--no-screen"])
    assert rc == 0


def test_launch_smoke_order_from_other_cwd(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = str(root / "src")
    env["DRY_RUN"] = "true"
    env["LIVE_TRADING"] = "false"
    env["STATE_PATH"] = str(tmp_path / "state.json")
    env["LOCK_PATH"] = str(tmp_path / "bot.lock")
    env["LOG_DIR"] = str(tmp_path / "logs")
    proc = subprocess.run(
        [sys.executable, "-m", "bitbank_bot.launch", "--smoke-order", "--no-screen"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "SMOKE_ORDER_OK SIMULATED_FILL" in out
    assert "/user/spot/order" not in out
    assert "create_order" not in out or "not calling Bitbank create_order" in out


def test_launch_bot_py_smoke_order_without_pythonpath(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["DRY_RUN"] = "true"
    env["LIVE_TRADING"] = "false"
    env["STATE_PATH"] = str(tmp_path / "state.json")
    env["LOCK_PATH"] = str(tmp_path / "bot.lock")
    env["LOG_DIR"] = str(tmp_path / "logs")
    proc = subprocess.run(
        [sys.executable, str(root / "launch_bot.py"), "--execute", "--no-screen"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "SMOKE_ORDER_OK SIMULATED_FILL" in out
    assert "/user/spot/order" not in out


def test_run_transaction_sh_from_other_cwd(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["DRY_RUN"] = "true"
    env["LIVE_TRADING"] = "false"
    env["STATE_PATH"] = str(tmp_path / "state.json")
    env["LOCK_PATH"] = str(tmp_path / "bot.lock")
    env["LOG_DIR"] = str(tmp_path / "logs")
    proc = subprocess.run(
        ["bash", str(root / "run_transaction.sh")],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "SMOKE_ORDER_OK SIMULATED_FILL" in out
    assert "may_place_live_orders: False" in out
    assert "/user/spot/order" not in out


def test_start_sh_smoke_order_from_other_cwd(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["DRY_RUN"] = "true"
    env["LIVE_TRADING"] = "false"
    env["STATE_PATH"] = str(tmp_path / "state.json")
    env["LOCK_PATH"] = str(tmp_path / "bot.lock")
    env["LOG_DIR"] = str(tmp_path / "logs")
    proc = subprocess.run(
        ["bash", str(root / "start.sh"), "--smoke-order", "--no-screen"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "SMOKE_ORDER_OK SIMULATED_FILL" in out
    assert "may_place_live_orders: False" in out
    assert LIVE_CONFIRM_PHRASE not in out or "YES_I_ACCEPT" not in proc.stdout
