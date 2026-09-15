"""Process boot: cwd, UTF-8 stdio, and a line the operator can see immediately."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def repo_root_from_here(here: Path) -> Path:
    here = here.resolve()
    if here.is_file():
        here = here.parent
    for candidate in (here, *here.parents):
        if (candidate / "src" / "bitbank_bot" / "main.py").is_file():
            return candidate
    return here


def prepare_process(root: Path | None = None) -> Path:
    """chdir to the repo and force UTF-8 so the first line is never silent."""
    root = repo_root_from_here(root or Path.cwd())
    os.chdir(root)
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    return root


def announce(message: str) -> None:
    line = message if message.endswith("\n") else message + "\n"
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.write(line)
            stream.flush()
            return
        except Exception:
            continue
