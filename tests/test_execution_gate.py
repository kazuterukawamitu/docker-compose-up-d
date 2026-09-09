from __future__ import annotations

from decimal import Decimal

from bitbank_bot.connection_manager import ConnectionManager
from bitbank_bot.execution_gate import ExecutionGate
from bitbank_bot.strategy import Signal
from tests.helpers import cfg


def _ok_kwargs(**extra):
    base = dict(
        signal=Signal("BUY1", "buy", Decimal("0.03"), "t"),
        amount=Decimal("0.001"),
        price=Decimal("10000000"),
        market_data_real=True,
        market_data_fresh=True,
        connection=ConnectionManager().snapshot(),
        private_api_ok=True,
        balance_ok=True,
        kill_switch=False,
        pending_order=False,
        open_orders=0,
    )
    base.update(extra)
    return base


def test_dry_run_blocks() -> None:
    gate = ExecutionGate(cfg())
    result = gate.evaluate(**_ok_kwargs())
    assert result.blocked
    assert result.reason == "trading_mode_not_dry_run"


def test_live_ready_would_submit() -> None:
    c = cfg(dry_run=False, live_trading=False, trading_mode="LIVE_READY")
    result = ExecutionGate(c).evaluate(**_ok_kwargs())
    assert result.would_submit
    assert result.reason == "live_ready"


def test_live_opens_when_confirmed() -> None:
    c = cfg(
        dry_run=False,
        live_trading=True,
        trading_mode="LIVE",
        live_trading_confirm=True,
        api_key="k",
        api_secret="s",
    )
    result = ExecutionGate(c).evaluate(**_ok_kwargs())
    assert result.allowed
    assert result.reason == "ok"


def test_synthetic_blocks_live() -> None:
    c = cfg(
        dry_run=False,
        live_trading=True,
        trading_mode="LIVE",
        live_trading_confirm=True,
        api_key="k",
        api_secret="s",
    )
    result = ExecutionGate(c).evaluate(**_ok_kwargs(market_data_real=False))
    assert result.blocked
    assert result.reason == "market_data_real"
