from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_gap_agent_passes() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gap_agent.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ALL PASS" in proc.stdout


def test_bug_scan_passes() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "bug_scan.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS" in proc.stdout


def test_paste_sh_exists() -> None:
    text = (ROOT / "paste.sh").read_text(encoding="utf-8")
    assert "run.py" in text
