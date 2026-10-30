"""Compile / pytest / ruff (safe select only). Never places orders."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from bitbank_bot.dual_run import repo_root

SAFE_RUFF = ["E9", "F63", "F7", "F82"]


def _run(cmd: list[str], cwd: Path, env: dict[str, str]) -> int:
    print("+", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=cwd, env=env)
    return int(proc.returncode)


def run_quality(root: Path | None = None) -> int:
    base = root or repo_root()
    env = os.environ.copy()
    env["DRY_RUN"] = "true"
    env["LIVE_TRADING"] = "false"
    env["PYTHONPATH"] = str(base / "src") + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    py = sys.executable
    rc = _run(
        [
            py,
            "-m",
            "compileall",
            "-q",
            "src",
            "main.py",
            "run.py",
            "diagnostics.py",
            "scripts",
            "docker",
        ],
        base,
        env,
    )
    if rc != 0:
        return rc
    rc = _run([py, "-m", "pytest", "-q"], base, env)
    if rc != 0:
        return rc
    rc = _run(
        [
            py,
            "-m",
            "ruff",
            "check",
            "--select",
            ",".join(SAFE_RUFF),
            "src",
            "tests",
            "scripts",
            "docker",
            "main.py",
            "run.py",
            "diagnostics.py",
        ],
        base,
        env,
    )
    return rc


def main(argv: list[str] | None = None) -> int:
    del argv
    return run_quality()


if __name__ == "__main__":
    raise SystemExit(main())
