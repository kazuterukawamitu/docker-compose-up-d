from __future__ import annotations

from decimal import Decimal

from bitbank_bot.execution_gate import evaluate
from bitbank_bot.strategy import Signal
from tests.helpers import cfg


def _buy() -> Signal:
    return Signal("BUY1", "buy", Decimal("0.03"), "test")


def test_dry_run_allows_paper() -> None:
    decision = evaluate(cfg(dry_run=True, live_trading=False), _buy(), market_data_real=True)
    assert decision.allowed is True
    assert decision.live is False
    assert decision.reason == "DRY_RUN"


def test_synthetic_blocks_live() -> None:
    c = cfg(dry_run=False, live_trading=True, api_key="k", api_secret="s")
    decision = evaluate(c, _buy(), market_data_real=False)
    assert decision.allowed is False
    assert decision.reason == "SYNTHETIC_DATA"


def test_live_ready_would_submit() -> None:
    c = cfg(dry_run=True, live_trading=False, live_ready=True)
    decision = evaluate(c, _buy(), market_data_real=True)
    assert decision.allowed is True
    assert decision.would_submit is True
    assert decision.live is False
    assert decision.reason == "LIVE_READY"


def test_live_allows_post() -> None:
    c = cfg(dry_run=False, live_trading=True, api_key="k", api_secret="s")
    decision = evaluate(c, _buy(), market_data_real=True)
    assert decision.allowed is True
    assert decision.live is True


def test_hold_blocked() -> None:
    decision = evaluate(cfg(), Signal.hold("no_buy_setup"), market_data_real=True)
    assert decision.allowed is False
    assert decision.reason == "NO_VALID_SIGNAL"


def test_kill_switch() -> None:
    decision = evaluate(cfg(), _buy(), market_data_real=True, kill_switch=True)
    assert decision.allowed is False
    assert decision.reason == "KILL_SWITCH"


def test_amount_reason() -> None:
    decision = evaluate(
        cfg(),
        _buy(),
        market_data_real=True,
        amount_ok=False,
        amount_reason="below_min_amount",
    )
    assert decision.allowed is False
    assert decision.reason == "below_min_amount"
