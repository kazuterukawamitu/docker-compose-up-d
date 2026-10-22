"""LIVE readiness report. Never places an order and never flips DRY_RUN."""

from __future__ import annotations

from pathlib import Path

from bitbank_bot.config import Config
from bitbank_bot.money import D, ZERO

FIXED_LIVE_LOT = D("0.001")


def live_blockers(cfg: Config) -> list[str]:
    """Reasons this process must not be treated as LIVE-ready.

    An empty list means the flags, keys, lot size, and stop are in place.
    It is not proof that the exchange will accept an order.
    """
    blockers: list[str] = []
    if cfg.dry_run:
        blockers.append("dry_run")
    if not cfg.live_trading:
        blockers.append("live_trading_off")
    if not cfg.has_keys:
        blockers.append("missing_keys")
    if cfg.fixed_order_btc != FIXED_LIVE_LOT:
        blockers.append("fixed_order_not_0.001")
    if cfg.stop_loss_pct <= ZERO:
        blockers.append("stop_loss_disabled")
    if cfg.kill_switch or Path(cfg.kill_switch_path).exists():
        blockers.append("kill_switch")
    if cfg.order_type not in {"limit", "market"}:
        blockers.append("order_type")
    return blockers


def live_ready(cfg: Config) -> bool:
    return not live_blockers(cfg)


def describe(cfg: Config) -> dict[str, object]:
    blockers = live_blockers(cfg)
    return {
        "live_ready": not blockers,
        "blockers": blockers,
        "pair": cfg.pair,
        "dry_run": cfg.dry_run,
        "live_trading": cfg.live_trading,
        "may_place_live_orders": cfg.may_place_live_orders,
        "fixed_order_btc": str(cfg.fixed_order_btc),
        "stop_loss_pct": str(cfg.stop_loss_pct),
        "sell_order_timeout_seconds": cfg.sell_order_timeout_seconds,
        "pending_order_timeout_seconds": cfg.pending_order_timeout_seconds,
        "orders_submitted": 0,
    }
