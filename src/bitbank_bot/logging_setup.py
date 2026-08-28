"""Structured logging with secret redaction and rotating files under logs/."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterable

_HEX64 = re.compile(r"(?i)(signature[\"':=\s]+)[0-9a-f]{64}")
_SECRET_KEYS = ("api_secret", "access-signature", "bitbank_api_secret", "hmac")


class StageFilter(logging.Filter):
    def __init__(self, secrets: Iterable[str] = ()) -> None:
        super().__init__()
        self._secrets = [s for s in secrets if s and len(s) > 3]

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "stage"):
            record.stage = "APP"
        record.msg = redact(str(record.getMessage()), self._secrets)
        record.args = ()
        return True


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    text = _HEX64.sub(r"\1***", text)
    for key in _SECRET_KEYS:
        text = re.sub(
            rf"(?i)({re.escape(key)}[\"':=\s]+)[^,\s]+",
            r"\1***",
            text,
        )
    return text


def setup_logging(
    log_dir: str | Path = "logs",
    level: str = "INFO",
    secrets: Iterable[str] = (),
) -> logging.Logger:
    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("bitbank_bot")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(stage)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    stream.addFilter(StageFilter(secrets))
    file_handler = RotatingFileHandler(
        path / "bot.log",
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.addFilter(StageFilter(secrets))
    logger.addHandler(stream)
    logger.addHandler(file_handler)
    return logger


def slog(stage: str, msg: str, level: int = logging.INFO, **fields: Any) -> None:
    logger = logging.getLogger("bitbank_bot")
    extra_bits = " ".join(f"{k}={v}" for k, v in fields.items())
    text = msg if not extra_bits else f"{msg} {extra_bits}"
    logger.log(level, text, extra={"stage": stage})
