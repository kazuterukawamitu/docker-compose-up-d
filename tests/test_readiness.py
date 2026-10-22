from __future__ import annotations

from decimal import Decimal

from bitbank_bot.readiness import describe, live_ready
from tests.helpers import cfg


def test_default_config_is_not_live_ready() -> None:
    report = describe(cfg())
    assert report["live_ready"] is False
    assert report["orders_submitted"] == 0
    blockers = report["blockers"]
    assert "dry_run" in blockers
    assert "missing_keys" in blockers


def test_live_ready_requires_flags_keys_lot_and_stop() -> None:
    blocked = cfg(
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
        fixed_order_btc=Decimal("0.01"),
    )
    assert live_ready(blocked) is False
    ready = cfg(
        dry_run=False,
        live_trading=True,
        api_key="k",
        api_secret="s",
        kill_switch_path="data/does-not-exist-KILL",
    )
    assert live_ready(ready) is True
    assert ready.may_place_live_orders is True
