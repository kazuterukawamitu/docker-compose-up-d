from __future__ import annotations

import os
import py_compile
import stat
import subprocess
import sys
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_iterm15_compiles_and_is_safe() -> None:
    path = _root() / "iterm15"
    assert path.is_file()
    assert path.stat().st_mode & stat.S_IXUSR
    text = path.read_text(encoding="utf-8")
    compile(text, str(path), "exec")
    py_compile.compile(str(path), doraise=True)
    assert text.startswith("#!/usr/bin/env python3")
    assert "create_order(" not in text
    assert "TRADING_MODE=live" not in text
    assert "LIVE_TRADING=true" not in text
    assert "!" not in text.split("Paste this ONE line", 1)[-1].split("After that file exists", 1)[0]


def test_iterm15_runs_from_other_cwd(tmp_path) -> None:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["HOME"] = str(tmp_path / "home")
    (tmp_path / "home").mkdir()
    proc = subprocess.run(
        [sys.executable, str(_root() / "iterm15"), "--once", "--synthetic", "--no-screen"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    combined = proc.stdout + proc.stderr
    assert "取引画面" in combined
    assert "DRY_RUN" in combined
    assert "run complete" in combined
    assert "starting Bitbank DRY_RUN" in combined


def test_iterm15_uses_copied_run_py_without_repo(tmp_path) -> None:
    copied_launcher = tmp_path / "iterm15"
    copied_run = tmp_path / "run.py"
    copied_launcher.write_text((_root() / "iterm15").read_text(encoding="utf-8"), encoding="utf-8")
    copied_run.write_text((_root() / "run.py").read_text(encoding="utf-8"), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["HOME"] = str(tmp_path / "home")
    (tmp_path / "home").mkdir()
    proc = subprocess.run(
        [sys.executable, str(copied_launcher), "--once", "--synthetic", "--no-screen"],
        cwd=str(tmp_path / "home"),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "Bitbank  BTC/JPY  取引画面" in proc.stdout
    assert "DRY_RUN" in proc.stdout


def test_readme_iterm15_one_liner_has_no_relative_dot_slash() -> None:
    text = (_root() / "README.md").read_text(encoding="utf-8")
    assert "python3 \"$HOME/iterm15\"" in text
    assert "curl -fsSL" in text
    assert "iterm15" in text
    assert ' -o "$HOME/iterm15" && python3 "$HOME/iterm15"' in text
