#!/usr/bin/env python3
"""Path-safe program launcher. Does not need PYTHONPATH or pip install -e.

start.sh execs this file with the venv interpreter. It puts ``src/`` on
sys.path, writes a venv .pth so ``python -m bitbank_bot`` also works, then
runs ``bitbank_bot.launch``.

Never places a live Bitbank order by itself. Paper fills: --smoke-order / --execute.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _ensure_src_on_path(root: Path) -> None:
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


def _write_venv_pth(root: Path) -> None:
    """So ``.venv/bin/python -m bitbank_bot.launch`` works without PYTHONPATH."""
    venv = (root / ".venv").resolve()
    try:
        prefix = Path(sys.prefix).resolve()
    except OSError:
        return
    if prefix != venv:
        return
    try:
        import sysconfig

        site = Path(sysconfig.get_path("purelib"))
    except Exception:
        return
    if not site.is_dir():
        return
    pth = site / "bitbank_bot_src.pth"
    payload = str(root / "src") + "\n"
    try:
        if pth.is_file() and pth.read_text(encoding="utf-8") == payload:
            return
        pth.write_text(payload, encoding="utf-8")
    except OSError:
        return


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    _ensure_src_on_path(root)
    _write_venv_pth(root)
    from bitbank_bot.launch import main as launch_main

    return int(launch_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
