from __future__ import annotations

import json
import logging
import logging.handlers
import re
from pathlib import Path
from typing import Any

_SECRET_KEYS = re.compile(
    r"(api[_-]?key|api[_-]?secret|access[_-]?key|access[_-]?signature|secret|token|password)",
    re.IGNORECASE,
)
_UUID_LIKE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_HEX_SECRET = re.compile(r"\b[0-9a-f]{32,}\b", re.IGNORECASE)


def redact(text: str) -> str:
    redacted = _UUID_LIKE.sub("[REDACTED]", text)
    redacted = _HEX_SECRET.sub("[REDACTED]", redacted)
    return redacted


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _redact_value(k, v) for k, v in record.args.items()}
            else:
                record.args = tuple(redact(str(a)) if isinstance(a, str) else a for a in record.args)
        return True


def _redact_value(key: str, value: Any) -> Any:
    if _SECRET_KEYS.search(key):
        return "[REDACTED]"
    if isinstance(value, str):
        return redact(value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(log_dir: Path, level: str = "INFO") -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    filt = RedactingFilter()
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    console.addFilter(filt)
    root.addHandler(console)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "bot.log",
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(JsonFormatter())
    file_handler.addFilter(filt)
    root.addHandler(file_handler)

    jsonl = logging.handlers.RotatingFileHandler(
        log_dir / "events.jsonl",
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    jsonl.setFormatter(JsonFormatter())
    jsonl.addFilter(filt)
    logging.getLogger("bitbank_bot.events").addHandler(jsonl)
    logging.getLogger("bitbank_bot.events").propagate = True
