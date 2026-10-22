"""Read-only comparison of local pending state with exchange order rows."""

from __future__ import annotations

from dataclasses import dataclass

_CANCELED = frozenset(
    {
        "CANCELED",
        "CANCELED_UNFILLED",
        "CANCELED_PARTIALLY_FILLED",
        "REJECTED",
        "EXPIRED",
    }
)


@dataclass(frozen=True)
class ReconcileDecision:
    action: str
    order_id: str | None
    reason: str


def decide_reconcile(
    local_order_id: str | None,
    active_order_ids: list[str],
    order_status: str | None,
) -> ReconcileDecision:
    """Decide keep, clear, or adopt. Never instructs a sell of extra wallet BTC.

    ``order_status is None`` means the row could not be read, so a local pending
    order stays in place. A full fill stays pending so the poll path can book it.
    """
    active = {str(item) for item in active_order_ids if item}
    if local_order_id:
        if local_order_id in active:
            return ReconcileDecision("keep", local_order_id, "still_active")
        if order_status is None:
            return ReconcileDecision("keep", local_order_id, "status_unknown")
        status = order_status.strip().upper()
        if status in _CANCELED or status.startswith("CANCELED"):
            return ReconcileDecision("clear", local_order_id, "canceled_on_exchange")
        if status in {"FULLY_FILLED", "PARTIALLY_FILLED"}:
            return ReconcileDecision("keep", local_order_id, "await_poll")
        return ReconcileDecision("keep", local_order_id, "unconfirmed")
    if active_order_ids:
        first = str(active_order_ids[0])
        return ReconcileDecision("adopt", first, "exchange_order_without_local")
    return ReconcileDecision("noop", None, "flat")
