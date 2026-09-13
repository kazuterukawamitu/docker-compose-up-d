"""Filesystem helpers so the bot starts from any cwd / invocation style."""

from __future__ import annotations

import sys
from pathlib import Path


def package_dir() -> Path:
    return Path(__file__).resolve().parent


def src_dir() -> Path:
    return package_dir().parent


def repo_root() -> Path:
    src = src_dir()
    if src.name == "src":
        return src.parent
    return src


def ensure_import_path() -> Path:
    """Allow ``python3 src/bitbank_bot/main.py`` without PYTHONPATH."""
    root = str(src_dir())
    if root not in sys.path:
        sys.path.insert(0, root)
    return src_dir()


def find_run_py() -> Path | None:
    candidate = repo_root() / "run.py"
    return candidate if candidate.is_file() else None
