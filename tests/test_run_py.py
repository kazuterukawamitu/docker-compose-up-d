from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_run_py_compiles() -> None:
    path = Path(__file__).resolve().parents[1] / "run.py"
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")
    assert "create_order(" not in source
    assert "/user/spot/order" not in source
    assert "urllib.request" in source


def test_run_py_once_synthetic_no_deps(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [sys.executable, str(root / "run.py"), "--once", "--synthetic", "--no-screen"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "取引画面" in proc.stdout
    assert "DRY_RUN" in proc.stdout
    assert "run complete" in proc.stdout


def test_run_py_works_without_repo_src(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    copied = tmp_path / "run.py"
    copied.write_text((root / "run.py").read_text(encoding="utf-8"), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [sys.executable, str(copied), "--once", "--synthetic", "--no-screen"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "Bitbank  BTC/JPY  取引画面" in proc.stdout


def test_start_sh_falls_back_to_run_py() -> None:
    text = Path(__file__).resolve().parents[1].joinpath("start.sh").read_text(encoding="utf-8")
    assert "run.py" in text
    assert "stdlib DRY_RUN" in text
