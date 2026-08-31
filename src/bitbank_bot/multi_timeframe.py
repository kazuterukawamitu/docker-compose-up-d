"""Eight-timeframe health fetch. Does not score-sum into a new strategy."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from bitbank_bot.config import TIMEFRAMES, Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.market_data import fetch_candles
from bitbank_bot.rest_client import RestClient

HIGHER_TFS = ("1w", "1d", "4h")


@dataclass(frozen=True)
class TimeframeHealth:
    alias: str
    candle_type: str
    ok: bool
    count: int
    last_ts: int | None
    reason: str


def load_all_timeframes(
    client: RestClient,
    cfg: Config,
    timeframes: Mapping[str, str] | None = None,
) -> dict[str, TimeframeHealth]:
    mapping = dict(timeframes or TIMEFRAMES)
    out: dict[str, TimeframeHealth] = {}
    for alias, candle_type in mapping.items():
        scoped = replace(cfg, candle_type=candle_type)
        try:
            candles = fetch_candles(client, scoped, latest_only=True)
        except Exception as exc:
            health = TimeframeHealth(
                alias, candle_type, False, 0, None, f"WAIT {type(exc).__name__}"
            )
            slog("MARKET", "WAIT", tf=alias, candle_type=candle_type, reason=health.reason)
            out[alias] = health
            continue
        if not candles:
            health = TimeframeHealth(alias, candle_type, False, 0, None, "WAIT empty")
            slog("MARKET", "WAIT", tf=alias, candle_type=candle_type, reason=health.reason)
            out[alias] = health
            continue
        last_ts = candles[-1].timestamp_ms
        health = TimeframeHealth(alias, candle_type, True, len(candles), last_ts, "MARKET DATA OK")
        slog(
            "MARKET",
            "MARKET DATA OK",
            tf=alias,
            candle_type=candle_type,
            count=len(candles),
        )
        out[alias] = health
    return out


def higher_tf_ready(health: Mapping[str, TimeframeHealth]) -> tuple[bool, str]:
    """Optional gate: block buys if 1w/1d/4h are missing. Not a new strategy."""
    for key in HIGHER_TFS:
        row = health.get(key)
        if row is None or not row.ok:
            return False, f"mtf_wait_{key}"
    return True, "ok"
