from __future__ import annotations

from decimal import Decimal

from bitbank_bot.execution_gate import ExecutionGate, GateContext
from bitbank_bot.strategy import Signal
from tests.helpers import cfg


def _ctx(**overrides: object) -> GateContext:
    base = dict(
        signal=Signal("BUY1", "buy", Decimal("0.03"), "test"),
        market_data_real=True,
        market_data_fresh=True,
        amount=Decimal("0.001"),
        amount_ok=True,
        kill_switch=False,
        pending_order=False,
        open_order_conflict=False,
        ws_stale=False,
        explicit_synthetic=False,
    )
    base.update(overrides)
    return GateContext(**base)  # type: ignore[arg-type]


def test_gate_allows_dry_run_real_data() -> None:
    gate = ExecutionGate(cfg())
    decision = gate.evaluate(_ctx())
    assert decision.allowed
    assert decision.reason == "ok"


def test_gate_blocks_synthetic_market_data() -> None:
    gate = ExecutionGate(cfg())
    decision = gate.evaluate(_ctx(market_data_real=False, explicit_synthetic=False))
    assert not decision.allowed
    assert decision.reason == "synthetic_market_data"


def test_gate_blocks_stale_and_ticker_mismatch() -> None:
    gate = ExecutionGate(cfg())
    stale = gate.evaluate(_ctx(market_data_fresh=False))
    assert not stale.allowed
    assert stale.reason == "STALE_MARKET_DATA"
    mismatch = gate.evaluate(_ctx(ticker_mismatch=True))
    assert not mismatch.allowed
    assert mismatch.reason == "STALE_MARKET_DATA"


def test_gate_blocks_kill_and_duplicate() -> None:
    gate = ExecutionGate(cfg())
    killed = gate.evaluate(_ctx(kill_switch=True))
    assert not killed.allowed
    assert killed.reason == "kill_switch"
    pending = gate.evaluate(_ctx(pending_order=True))
    assert not pending.allowed


def test_live_ready_still_requires_real_data() -> None:
    c = cfg(
        dry_run=False,
        live_trading=True,
        trading_mode="LIVE_READY",
        live_trading_confirm=False,
        api_key="k",
        api_secret="s",
    )
    gate = ExecutionGate(c)
    decision = gate.evaluate(_ctx(market_data_real=False))
    assert not decision.allowed
    assert decision.reason == "synthetic_market_data"
