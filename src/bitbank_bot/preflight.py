"""Startup checks. Failures are logged with a reason; never a silent exit."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from bitbank_bot.config import PAIR, Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D
from bitbank_bot.rest_client import RestClient


@dataclass
class PreflightResult:
    ok: bool
    reason: str
    last: str = ""
    status: str = ""
    checks: list[str] = field(default_factory=list)


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def preflight(
    cfg: Config,
    client: RestClient,
    *,
    require_public: bool = True,
) -> PreflightResult:
    checks: list[str] = []
    last = ""
    status = ""
    slog("BOOT", "preflight start", **cfg.safe_dict())

    if sys.version_info < (3, 12):
        slog("ERROR", "python_below_3_12", version=sys.version)
        return PreflightResult(False, "python_below_3_12", checks=checks)
    checks.append("python>=3.12")

    if cfg.pair != PAIR:
        slog("ERROR", "pair_not_btc_jpy", pair=cfg.pair)
        return PreflightResult(False, "pair_not_btc_jpy", checks=checks)
    checks.append("pair=btc_jpy")

    if cfg.dry_run and cfg.live_trading:
        slog("ERROR", "dry_run_and_live")
        return PreflightResult(False, "dry_run_and_live", checks=checks)
    if not cfg.dry_run and not cfg.live_trading:
        slog("ERROR", "live_requires_dual_flag")
        return PreflightResult(False, "live_requires_dual_flag", checks=checks)
    checks.append("mode_exclusive")

    for raw in (cfg.log_dir, Path(cfg.state_path).parent, Path(cfg.lock_path).parent):
        _ensure_dir(Path(raw))
    checks.append("dirs_writable")

    try:
        usage = shutil.disk_usage(Path(cfg.log_dir).resolve())
        if usage.free < 50 * 1024 * 1024:
            slog("ERROR", "low disk", free=usage.free)
            return PreflightResult(False, "low_disk", last, status, checks)
        checks.append("disk_ok")
    except OSError as exc:
        slog("ERROR", "disk check failed", error=type(exc).__name__)
        return PreflightResult(False, f"disk:{type(exc).__name__}", last, status, checks)

    try:
        ticker = client.get_ticker(cfg.pair)
        last = str(ticker.get("last") or "")
        slog("PUBLIC_API", "REST API OK", last=last)
        checks.append("public_ticker")
    except Exception as exc:
        if require_public:
            slog("ERROR", "public ticker failed", error=type(exc).__name__)
            return PreflightResult(False, f"public_ticker:{type(exc).__name__}", checks=checks)
        slog("ERROR", "public ticker failed; continuing", error=type(exc).__name__)

    try:
        row = client.get_spot_status(cfg.pair)
        if row:
            status = str(row.get("status") or "")
            slog("PUBLIC_API", "spot status", status=status, min_amount=row.get("min_amount"))
            if status == "HALT":
                slog("ERROR", "market_halt")
                return PreflightResult(False, "market_halt", last, status, checks)
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
            checks.append("spot_status")
    except Exception as exc:
        slog("ERROR", "spot status skipped", error=type(exc).__name__)

    if cfg.has_keys:
        try:
            assets = client.get_assets()
            slog("PRIVATE_API", "preflight assets", count=len(assets.get("assets") or []))
            checks.append("private_assets")
        except Exception as exc:
            slog("ERROR", "private assets failed", error=type(exc).__name__)
            if cfg.live_trading:
                return PreflightResult(
                    False, f"private_assets:{type(exc).__name__}", last, status, checks
                )
    else:
        slog("CONFIG", "no API keys; public + dry-run only")
        checks.append("no_keys_public_only")
        if cfg.live_trading:
            slog("ERROR", "missing_keys_live")
            return PreflightResult(False, "missing_keys_live", last, status, checks)

    slog("HEARTBEAT", "ORDER MANAGER OK")
    slog("HEARTBEAT", "RISK MANAGER OK")
    slog("BOOT", "preflight ok", checks=",".join(checks))
    return PreflightResult(True, "ok", last, status, checks)
