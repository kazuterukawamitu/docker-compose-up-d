from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

from bitbank_bot.reconciliation import reconcile
from tests.helpers import cfg


def test_reconcile_ok_when_balances_match() -> None:
    client = MagicMock()
    client.free_amount.side_effect = lambda asset: (
        Decimal("100000") if asset == "jpy" else Decimal("0.001")
    )
    client.get_active_orders.return_value = []
    report = reconcile(
        client,
        cfg(api_key="k", api_secret="s"),
        local_btc=Decimal("0.001"),
        pending_order_id=None,
    )
    assert report.ok
    assert report.reason == "ok"


def test_reconcile_mismatch_btc_and_pending() -> None:
    client = MagicMock()
    client.free_amount.side_effect = lambda asset: (
        Decimal("100000") if asset == "jpy" else Decimal("0.02")
    )
    client.get_active_orders.return_value = []
    client.get_order.return_value = {"status": "CANCELED", "executed_amount": "0"}
    report = reconcile(
        client,
        cfg(api_key="k", api_secret="s"),
        local_btc=Decimal("0.001"),
        pending_order_id="99",
    )
    assert not report.ok
    assert "btc_position" in report.mismatches
    assert "pending_missing" in report.mismatches


def test_reconcile_skips_without_keys() -> None:
    report = reconcile(None, cfg(), local_btc=Decimal("0"), pending_order_id=None)
    assert report.ok
    assert report.reason == "skipped_no_keys"
