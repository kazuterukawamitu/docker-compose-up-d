from __future__ import annotations

import logging
import os
import subprocess
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from bitbank_bot.config import LIVE_CONFIRM_PHRASE, MODE_LIVE, MODE_LIVE_READY, load_config
from bitbank_bot.launch import (
    classify_exit,
    diagnostics_lines,
    evaluate_live_guard,
    find_project_root,
    key_status,
    main,
    should_supervise,
    split_launch_argv,
    supervise_loop,
)
from bitbank_bot.logging_setup import setup_logging


def test_find_project_root_does_not_use_hardcoded_home() -> None:
    root = find_project_root()
    assert (root / "run.py").is_file()
    assert (root / "src" / "bitbank_bot" / "__init__.py").is_file()
    assert "/Users/kazuteru" not in str(root)


def test_diagnostics_hide_secrets_and_show_modes() -> None:
    cfg = load_config(
        environ={
            "BITBANK_API_KEY": "super-secret-key",
            "BITBANK_API_SECRET": "super-secret-value-16",
            "RATE_MODE": "fixed",
            "RECONCILE_EVERY_CYCLES": "10",
            "CANDLE_TYPE": "1hour",
        },
        load_default_dotenv=False,
    )
    text = "\n".join(
        diagnostics_lines(
            cfg,
            root=Path("/tmp/proj"),
            python_exe="python3",
            lock_text="data/bot.lock absent",
            kill_text="data/KILL absent",
        )
    )
    assert "super-secret" not in text
    assert "BITBANK_API_KEY: SET" in text
    assert "BITBANK_API_SECRET: SET" in text
    assert "RATE_MODE: fixed" in text
    assert "pair: btc_jpy" in text
    assert "RECONCILE_EVERY_CYCLES: 10" in text
    assert "CANDLE_TYPE: 1hour" in text
    assert "DRY_RUN/LIVE_READY/LIVE: DRY_RUN" in text
    assert key_status("") == "UNSET"


def test_live_guard_demotes_without_phrase() -> None:
    cfg = load_config(
        environ={"TRADING_MODE": "LIVE", "BITBANK_API_KEY": "k", "BITBANK_API_SECRET": "s"},
        load_default_dotenv=False,
    )
    allowed, mode, note = evaluate_live_guard(cfg)
    assert allowed is True
    assert mode == MODE_LIVE_READY
    assert "no POST" in note


def test_live_guard_allows_dual_auth_but_tests_do_not_post() -> None:
    cfg = load_config(
        environ={
            "TRADING_MODE": "LIVE",
            "LIVE_TRADING_CONFIRM": LIVE_CONFIRM_PHRASE,
            "BITBANK_API_KEY": "k",
            "BITBANK_API_SECRET": "s",
        },
        load_default_dotenv=False,
    )
    allowed, mode, note = evaluate_live_guard(cfg)
    assert allowed is True
    assert mode == MODE_LIVE
    assert "dual-auth" in note
    assert cfg.may_place_live_orders is True


def test_should_supervise_skips_oneshot_and_systemd() -> None:
    assert should_supervise(split_launch_argv([])) is True
    assert should_supervise(split_launch_argv(["--once"])) is False
    assert should_supervise(split_launch_argv(["--check-config"])) is False
    assert should_supervise(split_launch_argv(["--max-cycles", "2"])) is False
    assert should_supervise(split_launch_argv(["--no-supervise"])) is False
    assert should_supervise(split_launch_argv(["--supervise"]), {"INVOCATION_ID": "x"}) is True
    assert should_supervise(split_launch_argv([]), {"INVOCATION_ID": "x"}) is False


def test_supervise_does_not_restart_fatal_config() -> None:
    calls: list[list[str]] = []

    def run_fn(args: list[str]) -> int:
        calls.append(list(args))
        return 2

    rc = supervise_loop(
        ["--no-screen"],
        root=Path("."),
        enabled=True,
        sleep_fn=lambda _s: None,
        run_fn=run_fn,
    )
    assert rc == 2
    assert len(calls) == 1
    assert classify_exit(2) == "fatal"
    assert classify_exit(0) == "clean"
    assert classify_exit(1) == "crash"


def test_supervise_restarts_once_on_crash() -> None:
    n = {"i": 0}
    sleeps: list[float] = []

    def run_fn(_args: list[str]) -> int:
        n["i"] += 1
        return 1 if n["i"] == 1 else 0

    rc = supervise_loop(
        [],
        root=Path("."),
        enabled=True,
        sleep_fn=sleeps.append,
        run_fn=run_fn,
    )
    assert rc == 0
    assert n["i"] == 2
    assert sleeps == [2.0]


def test_launch_help() -> None:
    assert main(["--help"]) == 0


def test_launch_check_config() -> None:
    assert main(["--check-config"]) == 0


def test_start_sh_help_smoke() -> None:
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        ["bash", str(root / "start.sh"), "--help"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "DRY_RUN" in proc.stdout
    assert "start.sh" in proc.stdout
    assert "secret" not in proc.stdout.lower() or "without printing secrets" in proc.stdout


def test_launch_once_synthetic_no_order_post(tmp_path, monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["STATE_PATH"] = str(tmp_path / "state.json")
    env["LOCK_PATH"] = str(tmp_path / "bot.lock")
    env["LOG_DIR"] = str(tmp_path / "logs")
    env["DRY_RUN"] = "true"
    env["LIVE_TRADING"] = "false"
    env["ENABLE_WEBSOCKET"] = "false"
    env["PYTHONPATH"] = str(root / "src")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "bitbank_bot.launch",
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
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "RATE_MODE:" in proc.stdout
    assert "BITBANK_API_KEY: UNSET" in proc.stdout or "BITBANK_API_KEY: SET" in proc.stdout
    assert "super-secret" not in out
    assert "/user/spot/order" not in out
    assert "create_order" not in out
    assert "run_once complete" in proc.stdout


def test_rotating_log_handler(tmp_path) -> None:
    setup_logging("INFO", str(tmp_path), console=False)
    handlers = logging.getLogger("bitbank_bot").handlers
    assert any(isinstance(h, RotatingFileHandler) for h in handlers)
