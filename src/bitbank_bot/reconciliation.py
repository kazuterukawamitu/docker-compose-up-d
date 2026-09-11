"""Treat Bitbank private balances and open orders as source of truth."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO
from bitbank_bot.rest_client import BitbankAPIError, coerce_active_orders

_FILLED_STATUSES = frozenset(
    {
        "FULLY_FILLED",
        "CANCELED_PARTIALLY_FILLED",
        "CANCELLED_PARTIALLY_FILLED",
    }
)


class ReconcileClient(Protocol):
    def free_amount(self, asset: str) -> Decimal: ...

    def get_active_orders(self, pair: str) -> list[dict[str, Any]]: ...

    def get_order(self, pair: str, order_id: str) -> dict[str, Any]: ...


@dataclass
class ReconcileReport:
    ok: bool
    reason: str
    bitbank_jpy: Decimal = ZERO
    bitbank_btc: Decimal = ZERO
    local_btc: Decimal = ZERO
    open_orders: int = 0
    mismatches: list[str] = field(default_factory=list)


def _order_status(raw: dict[str, Any]) -> str:
    return str(raw.get("status") or "").upper().replace(" ", "_").replace("-", "_")


def reconcile(
    client: ReconcileClient | None,
    cfg: Config,
    *,
    local_btc: Decimal,
    pending_order_id: str | None,
    paper_jpy: Decimal | None = None,
    paper_btc: Decimal | None = None,
) -> ReconcileReport:
    if client is None or not cfg.has_keys:
        slog("RECONCILE", "skipped; no private client")
        return ReconcileReport(True, "skipped_no_keys")
    try:
        jpy = client.free_amount("jpy")
        btc = client.free_amount("btc")
        opens = coerce_active_orders(client.get_active_orders(cfg.pair))
    except Exception as exc:
        slog("RECONCILE", "failed", error=type(exc).__name__)
        return ReconcileReport(False, "reconcile_failed")
    mismatches: list[str] = []
    local = D(local_btc)
    if abs(btc - local) > cfg.min_amount_btc:
        mismatches.append("btc_position")
    if pending_order_id:
        ids = {str(row.get("order_id") or "") for row in opens}
        if pending_order_id not in ids:
            try:
                remote = client.get_order(cfg.pair, pending_order_id)
                if not isinstance(remote, dict):
                    raise BitbankAPIError("order_unreadable")
                status = _order_status(remote)
                executed = D(remote.get("executed_amount") or 0)
                if executed > ZERO or status in _FILLED_STATUSES:
                    mismatches.append("pending_filled_unapplied")
                else:
                    mismatches.append("pending_missing")
            except Exception as exc:
                slog("RECONCILE", "pending get_order failed", error=type(exc).__name__)
                mismatches.append("pending_lookup_failed")
    if paper_jpy is not None and cfg.dry_run:
        slog(
            "RECONCILE",
            "paper vs bitbank (informational)",
            paper_jpy=str(paper_jpy),
            paper_btc=str(paper_btc or ZERO),
            bitbank_jpy=str(jpy),
            bitbank_btc=str(btc),
        )
    report = ReconcileReport(
        ok=not mismatches,
        reason="mismatch" if mismatches else "ok",
        bitbank_jpy=jpy,
        bitbank_btc=btc,
        local_btc=local,
        open_orders=len(opens),
        mismatches=mismatches,
    )
    stage = "RECONCILE_MISMATCH" if mismatches else "RECONCILE"
    slog(
        stage,
        "bitbank source of truth",
        reason=report.reason,
        bitbank_jpy=str(report.bitbank_jpy),
        bitbank_btc=str(report.bitbank_btc),
        local_btc=str(report.local_btc),
        open_orders=report.open_orders,
        mismatches=",".join(report.mismatches),
    )
    return report
