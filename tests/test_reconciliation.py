from __future__ import annotations

from decimal import Decimal
from typing import Any

from bitbank_bot.reconciliation import ReconciliationManager
from bitbank_bot.strategy import Position
from tests.helpers import cfg


class Fake:
    def __init__(self, jpy: str, btc: str, orders: list[dict[str, Any]] | None = None) -> None:
        self.jpy = jpy
        self.btc = btc
        self.orders = orders or []

    def free_amount(self, asset: str) -> Decimal:
        return Decimal(self.jpy if asset == "jpy" else self.btc)

    def get_active_orders(self, pair: str) -> list[dict[str, Any]]:
        return self.orders

    def get_order(self, pair: str, order_id: str) -> dict[str, Any]:
        return {"order_id": order_id, "status": "CANCELED", "executed_amount": "0"}


def test_skip_without_keys() -> None:
    report = ReconciliationManager(cfg(), None).run(
        position=None, pending_order_id=None, paper=True
    )
    assert report.ok
    assert report.action == "skipped_paper"


def test_external_btc_disables_new_buys() -> None:
    c = cfg(api_key="k", api_secret="s")
    report = ReconciliationManager(c, Fake("10000", "0.01")).run(
        position=None, pending_order_id=None, paper=False
    )
    assert report.disable_new_orders
    assert "exchange_btc_without_bot_position" in report.reasons


def test_clear_vanished_pending() -> None:
    c = cfg(api_key="k", api_secret="s")
    report = ReconciliationManager(c, Fake("10000", "0", [])).run(
        position=None, pending_order_id="99", paper=False
    )
    assert report.action == "clear_pending"


def test_position_from_dataclass() -> None:
    pos = Position(
        amount=Decimal("0.01"),
        average_price=Decimal("10000000"),
        tp_pct=Decimal("0.03"),
        entry_candle_index=1,
        entry_candle_ts=1,
        actual_execution_jpy=Decimal("100000"),
        kind="BUY1",
    )
    c = cfg(api_key="k", api_secret="s")
    report = ReconciliationManager(c, Fake("0", "0.00001")).run(
        position=pos, pending_order_id=None, paper=False
    )
    assert report.action == "clear_position"
