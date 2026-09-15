"""Per-attempt trace_id for signal → gate → order → fill → balance."""

from __future__ import annotations

import uuid
from typing import Any

from bitbank_bot.logging_setup import slog


def new_trace_id() -> str:
    return uuid.uuid4().hex[:12]


def checkpoint(trace_id: str, stage: str, status: str, **fields: Any) -> None:
    slog(
        stage,
        status,
        trace_id=trace_id,
        **fields,
    )
