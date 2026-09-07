"""Bitbank is the source of truth for balances and open orders."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO
from bitbank_bot.rest_client import BitbankAPIError, RestClient


@dataclass
class ReconcileReport:
    ok: bool
    reason: str
    jpy: Decimal
    btc: Decimal
    active_orders: int
    ambiguous: bool
    disable_new_orders: bool


class ReconciliationManager:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.last_report = ReconcileReport(
            True, "not_run", ZERO, ZERO, 0, False, False
        )
        self.disable_new_orders = False

    def sync(
        self,
        rest: RestClient | None,
        *,
        internal_btc: Decimal,
        pending_order_id: str | None,
        has_keys: bool,
    ) -> ReconcileReport:
        if not has_keys or rest is None:
            report = ReconcileReport(True, "public_or_paper", ZERO, ZERO, 0, False, False)
            self.last_report = report
            return report
        try:
            jpy = rest.free_amount("jpy")
            btc = rest.free_amount("btc")
            active = rest.get_active_orders(self.cfg.pair)
        except BitbankAPIError as exc:
            slog(
                "ERROR",
                "reconcile failed",
                error=type(exc).__name__,
                function="ReconciliationManager.sync",
                pair=self.cfg.pair,
            )
            self.disable_new_orders = True
            report = ReconcileReport(
                False, "reconcile_api_error", ZERO, ZERO, 0, True, True
            )
            self.last_report = report
            return report
        except Exception as exc:
            slog(
                "ERROR",
                "reconcile failed",
                error=type(exc).__name__,
                function="ReconciliationManager.sync",
                pair=self.cfg.pair,
            )
            self.disable_new_orders = True
            report = ReconcileReport(
                False, "reconcile_api_error", ZERO, ZERO, 0, True, True
            )
            self.last_report = report
            return report
        slog("BALANCE_FETCH", "OK", jpy=str(jpy), btc=str(btc), active=len(active))
        ambiguous = False
        reason = "ok"
        if pending_order_id:
            ids = {str(row.get("order_id") or "") for row in active}
            if pending_order_id not in ids:
                try:
                    raw = rest.get_order(self.cfg.pair, pending_order_id)
                    status = str(raw.get("status") or "").upper()
                    if status not in {
                        "FULLY_FILLED",
                        "CANCELED",
                        "CANCELLED",
                        "REJECTED",
                        "EXPIRED",
                        "UNFILLED",
                        "PARTIALLY_FILLED",
                    }:
                        ambiguous = True
                        reason = "unknown_order_status"
                    elif status in {"UNFILLED", "PARTIALLY_FILLED"} and pending_order_id not in ids:
                        ambiguous = True
                        reason = "pending_missing_from_active"
                except Exception as exc:
                    slog(
                        "ERROR",
                        "pending order lookup failed",
                        error=type(exc).__name__,
                        function="ReconciliationManager.sync",
                        order_id=pending_order_id,
                    )
                    ambiguous = True
                    reason = "unknown_order_status"
        if internal_btc > ZERO:
            drift = abs(D(btc) - D(internal_btc))
            if drift > self.cfg.min_amount_btc:
                slog(
                    "RISK",
                    "position/exchange BTC diverge; not inventing a trade",
                    exchange_btc=str(btc),
                    internal_btc=str(internal_btc),
                )
                if pending_order_id is None:
                    ambiguous = True
                    reason = "position_mismatch"
        if ambiguous:
            slog("ERROR", "reconcile ambiguous; disabling new orders", reason=reason)
            self.disable_new_orders = True
        else:
            self.disable_new_orders = False
        report = ReconcileReport(
            not ambiguous,
            reason,
            jpy,
            btc,
            len(active),
            ambiguous,
            self.disable_new_orders,
        )
        self.last_report = report
        slog(
            "POSITION_RECONCILED",
            "bitbank source of truth",
            jpy=str(jpy),
            btc=str(btc),
            active=len(active),
            ok=report.ok,
        )
        return report
