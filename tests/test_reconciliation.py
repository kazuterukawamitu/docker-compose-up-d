from __future__ import annotations

from decimal import Decimal
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


def test_reconcile_flags_bitbank_btc_when_local_is_flat() -> None:
    client = MagicMock()
    client.free_amount.side_effect = lambda asset: (
        Decimal("100000") if asset == "jpy" else Decimal("0.02")
    )
    client.get_active_orders.return_value = []
    report = reconcile(
        client,
        cfg(api_key="k", api_secret="s"),
        local_btc=Decimal("0"),
        pending_order_id=None,
    )
    assert not report.ok
    assert report.bitbank_btc == Decimal("0.02")
    assert report.local_btc == Decimal("0")
    assert report.open_orders == 0
    assert "btc_position" in report.mismatches


def test_reconcile_flags_pending_filled_unapplied() -> None:
    client = MagicMock()
    client.free_amount.side_effect = lambda asset: (
        Decimal("100000") if asset == "jpy" else Decimal("0")
    )
    client.get_active_orders.return_value = {}
    client.get_order.return_value = {
        "status": "FULLY_FILLED",
        "executed_amount": "0.001",
    }
    report = reconcile(
        client,
        cfg(api_key="k", api_secret="s"),
        local_btc=Decimal("0"),
        pending_order_id="42",
    )
    assert not report.ok
    assert "pending_filled_unapplied" in report.mismatches
    assert "pending_missing" not in report.mismatches


def test_reconcile_bitbank_canceled_unfilled_is_pending_missing() -> None:
    client = MagicMock()
    client.free_amount.return_value = Decimal("0")
    client.get_active_orders.return_value = {"orders": []}
    client.get_order.return_value = {
        "status": "CANCELED_UNFILLED",
        "executed_amount": "0",
    }
    report = reconcile(
        client,
        cfg(api_key="k", api_secret="s"),
        local_btc=Decimal("0"),
        pending_order_id="99",
    )
    assert not report.ok
    assert "pending_missing" in report.mismatches


def test_reconcile_id_map_orders_do_not_crash() -> None:
    client = MagicMock()
    client.free_amount.return_value = Decimal("0")
    client.get_active_orders.return_value = {
        "7": {"order_id": "7", "side": "buy"},
    }
    report = reconcile(
        client,
        cfg(api_key="k", api_secret="s"),
        local_btc=Decimal("0"),
        pending_order_id="7",
    )
    assert report.ok
    assert report.open_orders == 1
