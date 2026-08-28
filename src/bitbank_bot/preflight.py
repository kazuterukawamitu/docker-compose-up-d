"""Startup checks: internet/public ticker, optional private assets."""

from __future__ import annotations

from dataclasses import dataclass

from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D
from bitbank_bot.rest_client import RestClient


@dataclass
class PreflightResult:
    ok: bool
    reason: str
    ticker_last: str | None = None
    market_status: str | None = None


def preflight(cfg: Config, client: RestClient, require_public: bool = True) -> PreflightResult:
    slog("BOOT", "preflight start", dry_run=cfg.dry_run, live_trading=cfg.live_trading)
    last = None
    status = None
    try:
        ticker = client.get_ticker(cfg.pair)
        last = str(ticker.get("last") or "")
        slog("PUBLIC_API", "preflight ticker", last=last)
    except Exception as exc:
        if require_public:
            slog("ERROR", "public ticker failed", error=type(exc).__name__)
            return PreflightResult(False, f"public_ticker:{type(exc).__name__}")
        slog("ERROR", "public ticker failed; continuing", error=type(exc).__name__)
    try:
        row = client.get_spot_status(cfg.pair)
        if row:
            status = str(row.get("status") or "")
            slog("PUBLIC_API", "spot status", status=status, min_amount=row.get("min_amount"))
            if status == "HALT":
                return PreflightResult(False, "market_halt", last, status)
            if row.get("min_amount"):
                exch_min = D(row["min_amount"])
                if exch_min > cfg.min_amount_btc:
                    slog("RISK", "honoring exchange min_amount", min_amount=str(exch_min))
                    cfg.min_amount_btc = exch_min
            if row.get("limit_max_amount"):
                exch_max = D(row["limit_max_amount"])
                if exch_max < cfg.max_order_btc:
                    slog("RISK", "honoring exchange max_amount", max_amount=str(exch_max))
                    cfg.max_order_btc = exch_max
    except Exception as exc:
        slog("ERROR", "spot status skipped", error=type(exc).__name__)
    if cfg.has_keys:
        try:
            assets = client.get_assets()
            slog("PRIVATE_API", "preflight assets", count=len(assets.get("assets") or []))
        except Exception as exc:
            slog("ERROR", "private assets failed", error=type(exc).__name__)
            if cfg.live_trading:
                return PreflightResult(False, f"private_assets:{type(exc).__name__}", last, status)
    else:
        slog("CONFIG", "no API keys; public + dry-run only")
        if cfg.live_trading:
            return PreflightResult(False, "missing_keys_live", last, status)
    return PreflightResult(True, "ok", last, status)
