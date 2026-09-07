from __future__ import annotations

from decimal import Decimal

from bitbank_bot.execution_gate import ExecutionGate
from bitbank_bot.strategy import Signal
from tests.helpers import cfg, live_cfg


def _ok_kwargs(c, **overrides):
    base = dict(
        cfg=c,
        signal=Signal("BUY1", "buy", Decimal("0.03"), "t", strategy_name="granville"),
        market_data_real=True,
        market_data_fresh=True,
        private_api_ok=True,
        balance_ok=True,
        risk_ok=True,
        risk_reason="ok",
        kill_switch=False,
        amount=Decimal("0.001"),
        price=Decimal("10000000"),
        duplicate=False,
        open_order_conflict=False,
        atr_ok=True,
        connection_ok=True,
        recon_ok=True,
        quarantined=False,
        unknown_order=False,
    )
    base.update(overrides)
    return base


def test_dry_run_would_submit_not_live() -> None:
    gate = ExecutionGate()
    decision = gate.evaluate(**_ok_kwargs(cfg()))
    assert decision.ok
    assert decision.live_submit is False
    assert decision.would_submit is True
    assert decision.reason == "dry_run_would_submit"


def test_live_ready_would_submit() -> None:
    c = cfg(trading_mode="LIVE_READY", dry_run=False, live_trading=False)
    decision = ExecutionGate().evaluate(**_ok_kwargs(c))
    assert decision.ok
    assert decision.live_submit is False
    assert "would_submit" in decision.reason


def test_synthetic_blocks() -> None:
    decision = ExecutionGate().evaluate(**_ok_kwargs(cfg(), market_data_real=False))
    assert not decision.ok
    assert decision.reason == "synthetic_market_data"


def test_live_passes_when_dual_authorized() -> None:
    decision = ExecutionGate().evaluate(**_ok_kwargs(live_cfg()))
    assert decision.ok
    assert decision.live_submit is True


def test_amount_below_minimum() -> None:
    decision = ExecutionGate().evaluate(
        **_ok_kwargs(live_cfg(), amount=Decimal("0.00001"))
    )
    assert not decision.ok
    assert decision.reason == "amount_below_minimum"


def test_kill_switch() -> None:
    decision = ExecutionGate().evaluate(**_ok_kwargs(live_cfg(), kill_switch=True))
    assert not decision.ok
    assert decision.reason == "kill_switch"


def test_stale_and_unknown_order() -> None:
    g = ExecutionGate()
    assert g.evaluate(**_ok_kwargs(live_cfg(), market_data_fresh=False)).reason == (
        "stale_market_data"
    )
    assert g.evaluate(**_ok_kwargs(live_cfg(), unknown_order=True)).reason == (
        "unknown_order_status"
    )
