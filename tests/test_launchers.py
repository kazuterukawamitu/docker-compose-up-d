from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _env(tmp_path: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["STATE_PATH"] = str(tmp_path / "state.json")
    env["LOCK_PATH"] = str(tmp_path / "bot.lock")
    env["LOG_DIR"] = str(tmp_path / "logs")
    env["DRY_RUN"] = "true"
    env["LIVE_TRADING"] = "false"
    env["ENABLE_WEBSOCKET"] = "false"
    return env


def _run(args: list[str], tmp_path: Path, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd or ROOT),
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_closed_loop_review(tmp_path) -> None:
    proc = _run([sys.executable, str(ROOT / "closed_loop.py"), "--review"], tmp_path)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "LAUNCH_OK" in proc.stdout
    assert "python3 closed_loop.py" in proc.stdout


def test_closed_loop_verify_no_public(tmp_path) -> None:
    proc = _run(
        [sys.executable, str(ROOT / "closed_loop.py"), "--verify", "--no-public"],
        tmp_path,
    )
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "LAUNCH_OK" in out
    assert "run_once complete" in out
    assert "may_place_live_orders" in out


def test_src_main_py_without_pythonpath(tmp_path) -> None:
    proc = _run(
        [sys.executable, str(ROOT / "src" / "bitbank_bot" / "main.py"), "--check-config"],
        tmp_path,
    )
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "LAUNCH_OK" in out
    assert "No module named 'bitbank_bot'" not in out


def test_dash_m_bitbank_bot_from_repo_root(tmp_path) -> None:
    proc = _run([sys.executable, "-m", "bitbank_bot", "--check-config"], tmp_path)
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "LAUNCH_OK" in out
    assert "No module named 'bitbank_bot'" not in out


def test_root_main_py_check_config(tmp_path) -> None:
    proc = _run([sys.executable, str(ROOT / "main.py"), "--check-config"], tmp_path)
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "LAUNCH_OK" in out


def test_closed_loop_go_from_other_cwd(tmp_path) -> None:
    proc = _run(
        [sys.executable, str(ROOT / "closed_loop.py"), "--go"],
        tmp_path,
        cwd=tmp_path,
    )
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "LAUNCH_OK" in out
    assert "run_once complete" in out
    assert "No module named 'bitbank_bot'" not in out


def test_closed_loop_go_prints_launch_ok(tmp_path) -> None:
    proc = _run([sys.executable, str(ROOT / "closed_loop.py"), "--go"], tmp_path)
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "LAUNCH_OK" in proc.stdout
    assert "run_once complete" in out
