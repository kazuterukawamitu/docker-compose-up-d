from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from bitbank_bot.reconciliation import ReconciliationManager
from tests.helpers import cfg


def test_public_or_paper_ok() -> None:
    report = ReconciliationManager(cfg()).sync(
        None, internal_btc=Decimal("0"), pending_order_id=None, has_keys=False
    )
    assert report.ok
    assert report.reason == "public_or_paper"


def test_api_error_disables_orders() -> None:
    rest = MagicMock()
    rest.free_amount.side_effect = RuntimeError("offline")
    mgr = ReconciliationManager(cfg())
    report = mgr.sync(rest, internal_btc=Decimal("0"), pending_order_id=None, has_keys=True)
    assert not report.ok
    assert report.disable_new_orders
    assert mgr.disable_new_orders


def test_pending_missing_is_ambiguous() -> None:
    rest = MagicMock()
    rest.free_amount.side_effect = lambda asset: Decimal("1")
    rest.get_active_orders.return_value = []
    rest.get_order.return_value = {"status": "MYSTERY"}
    mgr = ReconciliationManager(cfg())
    report = mgr.sync(
        rest, internal_btc=Decimal("0"), pending_order_id="99", has_keys=True
    )
    assert report.ambiguous
    assert report.disable_new_orders
