from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path


def _load_launch():
    path = Path(__file__).resolve().parents[1] / "launch.py"
    spec = importlib.util.spec_from_file_location("bitbank_launch", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


launcher = _load_launch()


def test_launch_py_compiles() -> None:
    path = Path(__file__).resolve().parents[1] / "launch.py"
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")
    assert "create_order(" not in source
    assert "/user/spot/order" not in source
    assert "os.execv" in source


def test_choose_target_prefers_main_when_package_ready() -> None:
    root = Path(__file__).resolve().parents[1]
    target = launcher.choose_target(root)
    assert target.name in {"main.py", "run.py"}
    if launcher.package_ready(root):
        assert target.name == "main.py"


def test_build_command_forwards_args_without_injecting_once() -> None:
    root = Path(__file__).resolve().parents[1]
    cmd = launcher.build_command(sys.executable, root / "main.py", ["--screen"])
    assert cmd[0] == sys.executable
    assert cmd[1].endswith("main.py")
    assert cmd[2:] == ["--screen"]
    assert "--once" not in cmd


def test_launch_without_exec_prints_and_exits_zero(capsys) -> None:
    rc = launcher.launch(["--once", "--synthetic"], exec_target=False)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Bitbank BTC/JPY" in out
    assert "DRY_RUN" in out


def test_launch_py_starts_target_once_synthetic(tmp_path) -> None:
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
    combined = proc.stdout + proc.stderr
    assert "Bitbank BTC/JPY を起動します" in combined
    assert "create_order" not in combined
    assert "run_once complete" in combined or "run complete" in combined
