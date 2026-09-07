"""Structured startup logging. The bot must never exit silently."""

from __future__ import annotations

import json
import logging
import re
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger("bitbank_bot")
_CONFIGURED = False
_REQUEST_ID: ContextVar[str] = ContextVar("request_id", default="")
_CYCLE_FIELDS: ContextVar[dict[str, Any]] = ContextVar("cycle_fields", default={})

_SECRET_FIELD = re.compile(
    r"(?<!has_)(api[_-]?secret|access-signature|bitbank_api_secret|authorization)",
    re.IGNORECASE,
)
_HEX_SECRET = re.compile(r"\b[0-9a-f]{64}\b", re.IGNORECASE)


def redact(text: str) -> str:
    text = _SECRET_FIELD.sub("[REDACTED]", text)
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


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def set_request_id(request_id: str) -> None:
    _REQUEST_ID.set(request_id)


def set_cycle_fields(**fields: Any) -> None:
    current = dict(_CYCLE_FIELDS.get())
    current.update(fields)
    _CYCLE_FIELDS.set(current)


def clear_cycle_fields() -> None:
    _CYCLE_FIELDS.set({})


def setup_logging(
    level: str = "INFO",
    log_dir: str = "logs",
    *,
    console: bool = True,
) -> None:
    global _CONFIGURED
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("bitbank_bot")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    formatter = logging.Formatter("%(message)s")
    if console:
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(formatter)
        stream.addFilter(_RedactFilter())
        root.addHandler(stream)
    file_handler = RotatingFileHandler(
        Path(log_dir) / "bot.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
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
    request_id = _REQUEST_ID.get()
    if request_id:
        payload["request_id"] = request_id
    for key, value in _CYCLE_FIELDS.get().items():
        payload.setdefault(key, value)
    for key, value in fields.items():
        if key.lower().startswith("has_"):
            payload[key] = value
        elif _SECRET_FIELD.search(key):
            payload[key] = "[REDACTED]"
        else:
            payload[key] = value
    line = json.dumps(payload, default=str, ensure_ascii=False)
    _LOGGER.log(level, line)
