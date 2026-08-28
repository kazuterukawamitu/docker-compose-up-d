"""Rotating file logs. API keys and signatures are never written."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterable

from bitbank_bot.config import Settings

_SECRET_PATTERNS = (
    re.compile(r"(BITBANK_API_SECRET\s*[=:]\s*)\S+", re.I),
    re.compile(r"(BITBANK_API_KEY\s*[=:]\s*)\S+", re.I),
    re.compile(r"(ACCESS-SIGNATURE\s*[=:]\s*)\S+", re.I),
    re.compile(r"(ACCESS-KEY\s*[=:]\s*)\S+", re.I),
    re.compile(r"(api_secret\s*[=:]\s*['\"]?)[^'\"\s,]+", re.I),
    re.compile(r"(api_key\s*[=:]\s*['\"]?)[^'\"\s,]+", re.I),
    re.compile(r"(Bearer\s+)\S+", re.I),
)
_HEX64 = re.compile(r"(?i)(signature[\"':=\s]+)[0-9a-f]{64}")


class RedactFilter(logging.Filter):
    def __init__(self, secrets: tuple[str, ...] = ()) -> None:
        super().__init__()
        self._secrets = tuple(s for s in secrets if s)

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "stage"):
            record.stage = "APP"
        record.msg = self._redact(str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._redact(v) for k, v in record.args.items()}
            else:
                record.args = tuple(self._redact(a) for a in record.args)
        return True

    def _redact(self, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value
        for secret in self._secrets:
            if secret:
                text = text.replace(secret, "[REDACTED]")
        for pattern in _SECRET_PATTERNS:
            text = pattern.sub(r"\1[REDACTED]", text)
        text = _HEX64.sub(r"\1[REDACTED]", text)
        return text


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    filt = RedactFilter(tuple(secrets))
    result = filt._redact(text)
    return result if isinstance(result, str) else str(result)


def setup_logging(settings: Settings | str | Path = "logs", level: str | None = None) -> logging.Logger:
    if isinstance(settings, Settings):
        log_dir = Path(settings.log_dir)
        log_level = settings.log_level
        secrets = (settings.api_key, settings.api_secret)
    else:
        log_dir = Path(settings)
        log_level = level or "INFO"
        secrets = ()
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("bitbank_bot")
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    logger.handlers.clear()
    logger.propagate = False

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    redact_filter = RedactFilter(secrets=secrets)

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    stream.addFilter(redact_filter)
    logger.addHandler(stream)

    file_handler = RotatingFileHandler(
        log_dir / "bitbank_bot.log",
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.addFilter(redact_filter)
    logger.addHandler(file_handler)
    return logger


def slog(stage: str, msg: str, level: int = logging.INFO, **fields: Any) -> None:
    logger = logging.getLogger("bitbank_bot")
    extra = " ".join(f"{k}={v}" for k, v in fields.items())
    text = msg if not extra else f"{msg} {extra}"
    logger.log(level, "%s %s", stage, text)
