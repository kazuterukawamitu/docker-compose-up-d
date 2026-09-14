from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import launch as launch_mod  # noqa: E402


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
    assert "git clone" in text
    assert "~/main.py" in text


def test_clean_argv_strips_zero_width() -> None:
    assert launch_mod.clean_argv(["\u200b\u200b--doctor", " --once "]) == ["--doctor", "--once"]


def test_looks_like_bot_requires_package() -> None:
    root = Path(__file__).resolve().parents[1]
    assert launch_mod.looks_like_bot(root)
    assert not launch_mod.looks_like_bot(Path.home())


def test_missing_checkout_message_mentions_home_main_py() -> None:
    text = launch_mod.missing_checkout_message()
    assert "git clone" in text
    assert "~/main.py" in text
    assert "python@3.12" in text


def test_copied_launch_py_uses_bot_root(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    copied = tmp_path / "launch.py"
    copied.write_text((root / "launch.py").read_text(encoding="utf-8"), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["BITBANK_BOT_ROOT"] = str(root)
    env["BITBANK_NO_CLONE"] = "1"
    env["BITBANK_LAUNCH_PYTHON_OK"] = "1"
    proc = subprocess.run(
        [sys.executable, str(copied), "--version"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "bitbank-btc-jpy-bot" in proc.stdout


def test_copied_launch_py_without_checkout_explains(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    copied = tmp_path / "launch.py"
    copied.write_text((root / "launch.py").read_text(encoding="utf-8"), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["HOME"] = str(tmp_path / "home")
    env["BITBANK_BOT_ROOT"] = str(tmp_path / "missing-bot")
    env["BITBANK_NO_CLONE"] = "1"
    env["BITBANK_LAUNCH_PYTHON_OK"] = "1"
    Path(env["HOME"]).mkdir()
    proc = subprocess.run(
        [sys.executable, str(copied), "--version"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert proc.returncode == 2
    assert "git clone" in proc.stderr
    assert "~/main.py" in proc.stderr


def test_zwsp_version_flag() -> None:
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, str(root / "launch.py"), "\u200b\u200b--version"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "bitbank-btc-jpy-bot" in proc.stdout
