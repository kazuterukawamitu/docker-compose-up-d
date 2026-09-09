"""Canonical trading modes. LIVE never comes from a single flag."""

from __future__ import annotations

from enum import Enum

LIVE_CONFIRM_PHRASE = "YES_I_ACCEPT_REAL_MONEY_RISK"


class TradingMode(str, Enum):
    DRY_RUN = "DRY_RUN"
    LIVE_READY = "LIVE_READY"
    LIVE = "LIVE"


def normalize_trading_mode(raw: str | None) -> TradingMode | None:
    if raw is None or str(raw).strip() == "":
        return None
    key = str(raw).strip().upper().replace("-", "_")
    aliases = {
        "DRY": TradingMode.DRY_RUN,
        "DRY_RUN": TradingMode.DRY_RUN,
        "DRYRUN": TradingMode.DRY_RUN,
        "PAPER": TradingMode.DRY_RUN,
        "LIVE_READY": TradingMode.LIVE_READY,
        "LIVEREADY": TradingMode.LIVE_READY,
        "SIGNAL_ONLY": TradingMode.LIVE_READY,
        "LIVE": TradingMode.LIVE,
    }
    return aliases.get(key)


def confirm_live(phrase: str | None) -> bool:
    return (phrase or "").strip() == LIVE_CONFIRM_PHRASE


def resolve_trading_mode(
    *,
    explicit: TradingMode | None,
    dry_run: bool,
    live_trading: bool,
    live_confirmed: bool,
    has_keys: bool,
) -> TradingMode:
    """Resolve DRY_RUN / LIVE_READY / LIVE.

    LIVE requires explicit live intent, dual confirmation, and API keys.
    Missing confirmation demotes LIVE to LIVE_READY (full path, no POST).
    """
    if explicit is TradingMode.DRY_RUN:
        return TradingMode.DRY_RUN
    if explicit is TradingMode.LIVE:
        if live_confirmed and has_keys:
            return TradingMode.LIVE
        return TradingMode.LIVE_READY
    if explicit is TradingMode.LIVE_READY:
        return TradingMode.LIVE_READY
    if live_trading and not dry_run:
        if live_confirmed and has_keys:
            return TradingMode.LIVE
        return TradingMode.LIVE_READY
    if not dry_run:
        return TradingMode.LIVE_READY
    return TradingMode.DRY_RUN
