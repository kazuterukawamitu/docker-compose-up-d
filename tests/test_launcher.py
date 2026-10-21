from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RUN_SH_FORCE_STDLIB"] = "1"
    return subprocess.run(
        ["bash", str(ROOT / "run.sh"), *args],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_run_sh_help_has_commands_and_no_git() -> None:
    text = (ROOT / "run.sh").read_text(encoding="utf-8")
    start = (ROOT / "start.sh").read_text(encoding="utf-8")
    for word in ("help", "check", "dry", "once", "live-ready"):
        assert word in text
    for banned in ("git fetch", "git clone", "git checkout", "git pull"):
        assert banned not in text
        assert banned not in start
    assert "/run.sh" in text
    proc = _run(["help"])
    assert proc.returncode == 0, proc.stderr
    assert "does not place an order" in proc.stdout or "no Bitbank orders" in proc.stdout


def test_run_sh_check_and_once_do_not_need_git() -> None:
    check = _run(["check"])
    assert check.returncode == 0, check.stderr + check.stdout
    assert "check ok" in check.stdout
    assert "does not place an order" in check.stdout
    once = _run(["once"])
    assert once.returncode == 0, once.stderr + once.stdout
    assert "DRY_RUN" in once.stdout


def test_live_ready_does_not_order_when_dry_run() -> None:
    proc = _run(["live-ready"])
    assert proc.returncode == 2
    combined = proc.stdout + proc.stderr
    assert "not placing an order" in combined or "does not place an order" in combined
    assert "may_place_live_orders=False" in combined


def test_pack_source_script_has_no_ssh() -> None:
    text = (ROOT / "scripts" / "pack_source.sh").read_text(encoding="utf-8")
    assert "ssh" not in text
    assert "scp" not in text
    assert "git " not in text
