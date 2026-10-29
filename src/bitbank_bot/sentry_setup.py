"""Optional Sentry error reporting.

Enable with env ``SENTRY_DSN``. Never hard-code a DSN in the repository.
Initialize from Python (``python3 -c`` or this package), not by pasting
``import`` lines into zsh — the shell is not a Python interpreter.
"""

from __future__ import annotations

import os
from typing import Any


def init_sentry(*, release: str | None = None) -> bool:
    """Initialize sentry-sdk when ``SENTRY_DSN`` is set. Returns True if active."""
    dsn = (os.environ.get("SENTRY_DSN") or "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        return False
    options: dict[str, Any] = {
        "dsn": dsn,
        "traces_sample_rate": float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE") or "0"),
        "send_default_pii": False,
    }
    if release:
        options["release"] = release
    sentry_sdk.init(**options)
    return True
