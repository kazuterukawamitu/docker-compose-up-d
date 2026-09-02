from __future__ import annotations

import os
import py_compile
import subprocess
import sys
from pathlib import Path

from bitbank_bot.config import load_config
from bitbank_bot.main import build_parser, main


def test_compileall_src() -> None:
    root = Path(__file__).resolve().parents[1]
    for path in (root / "src").rglob("*.py"):
        py_compile.compile(str(path), doraise=True)
    py_compile.compile(str(root / "main.py"), doraise=True)
    diag = root / "diagnostics.py"
    if diag.is_file():
        py_compile.compile(str(diag), doraise=True)
    for path in (root / "scripts").rglob("*.py"):
        py_compile.compile(str(path), doraise=True)


def test_check_config_exit_zero() -> None:
    assert main(["--check-config"]) == 0


def test_default_cli_is_continuous_loop_not_once() -> None:
    args = build_parser().parse_args([])
    assert args.once is False
    assert args.synthetic is False
    assert args.max_cycles is None


def test_synthetic_does_not_imply_once() -> None:
    args = build_parser().parse_args(["--synthetic"])
    assert args.once is False
    assert args.synthetic is True


def test_start_sh_is_venv_loop_launcher() -> None:
    text = Path(__file__).resolve().parents[1].joinpath("start.sh").read_text(encoding="utf-8")
    assert ".venv" in text
    assert 'VPY="$VENV/bin/python"' in text
    assert "exec" in text
    after_exec = text.rsplit("exec", 1)[-1]
    assert "--once" not in after_exec
    assert "--screen" in text
    assert "取引画面" in text
    assert ".env.example" in text
    assert "python3.12" in text
    assert "python3" in text
    assert 'BOT_BRANCH="cursor/bitbank-audit-unify-f5fd"' in text


def test_loop_cli_exits_after_max_cycles(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("LOCK_PATH", str(tmp_path / "bot.lock"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("LIVE_TRADING", "false")
    monkeypatch.setenv("ENABLE_WEBSOCKET", "false")
    rc = main(
        ["--synthetic", "--dry-run", "--skip-lock", "--max-cycles", "2"]
    )
    assert rc == 0


def test_load_config_default_pair() -> None:
    cfg = load_config(environ={"DRY_RUN": "true"}, load_default_dotenv=False)
    assert cfg.pair == "btc_jpy"


def test_main_py_runs_without_pythonpath(tmp_path) -> None:
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
            str(root / "main.py"),
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
    assert "may_place_live_orders" in proc.stdout
    assert "run_once complete" in proc.stdout


def test_audit_script_runs_without_pythonpath() -> None:
    root = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [sys.executable, str(root / "scripts" / "bitbank_execution_audit.py")],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "No module named 'bitbank_bot'" not in proc.stderr
    assert "public ticker only" in proc.stdout or "ticker" in proc.stdout
