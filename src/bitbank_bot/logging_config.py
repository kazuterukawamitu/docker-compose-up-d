"""Rotating file + stderr logging. Secrets are filtered from log records."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_SECRET_KEYS = re.compile(
    r"(api[_-]?key|api[_-]?secret|access[_-]?signature|authorization)\s*[:=]\s*\S+",
    re.IGNORECASE,
)
_UUIDISH = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)


class SecretFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact(str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _redact(str(v)) for k, v in record.args.items()}
            else:
                record.args = tuple(_redact(str(a)) for a in record.args)
        return True


def _redact(text: str) -> str:
    text = _SECRET_KEYS.sub(lambda m: m.group(0).split("=")[0].split(":")[0] + "=***", text)
    return _UUIDISH.sub("********-****-****-****-************", text)


def setup_logging(log_dir: Path, level: str = "INFO") -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("bitbank_bot")
    logger.setLevel(level)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    file_handler = RotatingFileHandler(
        log_dir / "bot.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    secret_filter = SecretFilter()
    for handler in (file_handler, stream):
        handler.addFilter(secret_filter)
        logger.addHandler(handler)
    logger.propagate = False
    return logger
