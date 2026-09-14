from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("bitbank_launch", ROOT / "launch.py")
assert _SPEC and _SPEC.loader
_LAUNCH = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_LAUNCH)

LIVE_CONFIRM_OK = _LAUNCH.LIVE_CONFIRM_OK
PROGRAMS = _LAUNCH.PROGRAMS
REQUIRED_FILES = _LAUNCH.REQUIRED_FILES
_apply_mode = _LAUNCH._apply_mode
_has_keys = _LAUNCH._has_keys
_read_dotenv = _LAUNCH._read_dotenv
_split_argv = _LAUNCH._split_argv
filter_stdlib_argv = _LAUNCH.filter_stdlib_argv
main = _LAUNCH.main


def test_launch_py_compiles() -> None:
    path = Path(__file__).resolve().parents[1] / "launch.py"
    compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_split_argv_strips_live_flags() -> None:
    args, rest = _split_argv(["--live", "--once", "--synthetic"])
    assert args.live is True
    assert "--live" not in rest
    assert "--once" in rest


def test_check_alias() -> None:
    args, rest = _split_argv(["--check"])
    assert args.check is True
    assert rest[0] == "--check-config"


def test_has_keys_from_file() -> None:
    assert _has_keys({"BITBANK_API_KEY": "k", "BITBANK_API_SECRET": "s"})
    assert not _has_keys({"BITBANK_API_KEY": "", "BITBANK_API_SECRET": "s"})


def test_apply_live_refuses_without_keys(monkeypatch) -> None:
    monkeypatch.delenv("BITBANK_API_KEY", raising=False)
    monkeypatch.delenv("BITBANK_API_SECRET", raising=False)
    args, _ = _split_argv(["--live"])
    try:
        _apply_mode(args, {})
        raised = False
    except SystemExit as exc:
        raised = True
        assert exc.code == 2
    assert raised


def test_apply_live_sets_env_when_keys(monkeypatch) -> None:
    monkeypatch.setenv("BITBANK_API_KEY", "k")
    monkeypatch.setenv("BITBANK_API_SECRET", "s")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("LIVE_TRADING", "false")
    monkeypatch.setenv("LIVE_READY", "false")
    monkeypatch.delenv("LIVE_TRADING_CONFIRM", raising=False)
    args, _ = _split_argv(["--live"])
    mode = _apply_mode(args, {"BITBANK_API_KEY": "k", "BITBANK_API_SECRET": "s"})
    assert mode == "live"
    assert os.environ["DRY_RUN"] == "false"
    assert os.environ["LIVE_TRADING"] == "true"


def test_apply_live_degrades_on_bad_confirm(monkeypatch) -> None:
    monkeypatch.setenv("BITBANK_API_KEY", "k")
    monkeypatch.setenv("BITBANK_API_SECRET", "s")
    monkeypatch.setenv("LIVE_TRADING_CONFIRM", "no")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("LIVE_TRADING", "false")
    monkeypatch.setenv("LIVE_READY", "false")
    args, _ = _split_argv(["--live"])
    mode = _apply_mode(args, {"BITBANK_API_KEY": "k", "BITBANK_API_SECRET": "s"})
    assert mode == "live_ready"
    assert os.environ["LIVE_READY"] == "true"


def test_confirm_constant() -> None:
    assert LIVE_CONFIRM_OK == "YES_I_ACCEPT_REAL_MONEY_RISK"


def test_read_dotenv_skips_comments(tmp_path) -> None:
    path = tmp_path / ".env"
    path.write_text("# x\nDRY_RUN=true\n", encoding="utf-8")
    assert _read_dotenv(path)["DRY_RUN"] == "true"


def test_launch_check_config_subprocess(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["DRY_RUN"] = "true"
    env["LIVE_TRADING"] = "false"
    env["LIVE_READY"] = "false"
    env["TRADING_MODE"] = "dry_run"
    env["ENABLE_WEBSOCKET"] = "false"
    env["STATE_PATH"] = str(tmp_path / "state.json")
    env["LOCK_PATH"] = str(tmp_path / "bot.lock")
    env["LOG_DIR"] = str(tmp_path / "logs")
    proc = subprocess.run(
        [sys.executable, str(root / "launch.py"), "--check"],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "TRADING_MODE=dry_run" in proc.stdout
    assert "may_place_live_orders=false" in proc.stdout
    assert "config ok" in proc.stdout


def test_launch_live_without_keys_exits_2(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items()}
    env.pop("BITBANK_API_KEY", None)
    env.pop("BITBANK_API_SECRET", None)
    env["DRY_RUN"] = "true"
    proc = subprocess.run(
        [sys.executable, str(root / "launch.py"), "--live"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert proc.returncode == 2
    assert "LIVE refused" in proc.stderr
    assert "BITBANK_API_SECRET" not in proc.stdout or "missing" in proc.stderr


def test_filter_stdlib_argv_drops_package_flags() -> None:
    filtered = filter_stdlib_argv(
        [
            "--check-config",
            "--preflight",
            "--backtest",
            "--env-file",
            "/tmp/x.env",
            "--once",
            "--synthetic",
            "--max-cycles",
            "2",
            "--no-screen",
        ]
    )
    assert filtered == ["--once", "--synthetic", "--max-cycles", "2", "--no-screen"]


def test_programs_map_names_canonical_starter() -> None:
    names = [name for name, _role in PROGRAMS]
    assert names[0] == "launch.py"
    assert "main.py" in names
    assert "run.py" in names
    assert "start.sh" in names
    for name in REQUIRED_FILES:
        assert (ROOT / name).is_file(), name


def test_main_py_is_launch_alias() -> None:
    text = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "from launch import main" in text
    assert "create_order" not in text


def test_split_argv_forwards_env_file() -> None:
    args, rest = _split_argv(["--env-file", "/tmp/bot.env", "--once"])
    assert args.env_file == "/tmp/bot.env"
    assert rest[:2] == ["--env-file", "/tmp/bot.env"]
    assert "--once" in rest


def test_launch_programs_subprocess() -> None:
    env = {k: v for k, v in os.environ.items()}
    proc = subprocess.run(
        [sys.executable, str(ROOT / "launch.py"), "--programs"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "canonical_starter=launch.py" in proc.stdout
    assert "run.py: stdlib DRY_RUN" in proc.stdout


def test_launch_doctor_subprocess_hides_secrets(tmp_path) -> None:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["DRY_RUN"] = "true"
    env["LIVE_TRADING"] = "false"
    env["LIVE_READY"] = "false"
    env["TRADING_MODE"] = "dry_run"
    env["ENABLE_WEBSOCKET"] = "false"
    env["STATE_PATH"] = str(tmp_path / "state.json")
    env["LOCK_PATH"] = str(tmp_path / "bot.lock")
    env["LOG_DIR"] = str(tmp_path / "logs")
    env["BITBANK_API_KEY"] = "supersecretvalue123"
    env["BITBANK_API_SECRET"] = "supersecretsecret456"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "launch.py"), "--doctor"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined
    assert "DOCTOR" in proc.stdout
    assert "required_files=ok" in proc.stdout
    assert "doctor=ok" in proc.stdout
    assert "pair=btc_jpy" in proc.stdout
    assert "may_place_live_orders=false" in proc.stdout
    assert "supersecretvalue123" not in combined
    assert "supersecretsecret456" not in combined
    assert "has_api_keys=true" in proc.stdout


def test_launch_module_main_check(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("LIVE_TRADING", "false")
    monkeypatch.setenv("LIVE_READY", "false")
    monkeypatch.setenv("TRADING_MODE", "dry_run")
    monkeypatch.setenv("ENABLE_WEBSOCKET", "false")
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("LOCK_PATH", str(tmp_path / "bot.lock"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    assert main(["--check"]) == 0
