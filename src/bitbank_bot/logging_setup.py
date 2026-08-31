"""Structured startup logging. The bot must never exit silently."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger("bitbank_bot")
_CONFIGURED = False

_REDACT_KEYS = re.compile(
    r"(api[_-]?secret|access-signature|bitbank_api_secret|authorization)",
    re.IGNORECASE,
)
_HEX_SECRET = re.compile(r"\b[0-9a-f]{32,}\b", re.IGNORECASE)


def redact(text: str) -> str:
    if _REDACT_KEYS.search(text):
        return _REDACT_KEYS.sub("[REDACTED]", text)
    return _HEX_SECRET.sub("[REDACTED]", text)


class _RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: redact(str(v)) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact(str(a)) if isinstance(a, str) else a for a in record.args
                )
        return True


def setup_logging(level: str = "INFO", log_dir: str = "logs") -> None:
    global _CONFIGURED
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("bitbank_bot")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    formatter = logging.Formatter("%(message)s")
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    stream.addFilter(_RedactFilter())
    root.addHandler(stream)
    file_handler = logging.FileHandler(Path(log_dir) / "bot.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(_RedactFilter())
    root.addHandler(file_handler)
    _CONFIGURED = True


def slog(stage: str, message: str, *, level: int = logging.INFO, **fields: Any) -> None:
    if not _CONFIGURED:
        setup_logging()
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "msg": message,
    }
    for key, value in fields.items():
        if _REDACT_KEYS.search(key):
            payload[key] = "[REDACTED]"
        else:
            payload[key] = value
    line = json.dumps(payload, default=str, ensure_ascii=False)
    _LOGGER.log(level, line)
