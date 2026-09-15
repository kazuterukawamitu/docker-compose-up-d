"""Repo-root shim so `python3 -m bitbank_bot` works without PYTHONPATH.

The real package lives in src/bitbank_bot/. This directory only extends
__path__ so `import bitbank_bot.config` resolves there.
"""

from __future__ import annotations

from pathlib import Path

_REAL = Path(__file__).resolve().parent.parent / "src" / "bitbank_bot"
__path__ = [str(_REAL)]
__version__ = "0.1.0"
