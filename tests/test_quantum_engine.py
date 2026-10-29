from __future__ import annotations

from bitbank_bot.money import D
from bitbank_bot.quantum_engine import (
    adaptive_basin_hopping,
    build_quantum_view,
    gravity_well_escape_optimizer,
    multi_scenario_inference,
    probability_state_updater,
    self_healing_execution_guard,
)
from bitbank_bot.strategy import Position, Signal


def test_probability_normalizes() -> None:
    closes = [D(100 + i) for i in range(20)]
    up, down, flat = probability_state_updater(closes, entropy=D("0.2"))
    assert abs((up + down + flat) - D("1")) < D("0.0001")


def test_multi_scenario_three_worlds() -> None:
    closes = [D(100 + i) for i in range(15)]
    pos = Position(
        amount=D("0.001"),
        average_price=D("100"),
        tp_pct=D("0.03"),
        entry_candle_index=0,
        entry_candle_ts=0,
        actual_execution_jpy=D("0.1"),
        kind="BUY1",
    )
    scores = multi_scenario_inference(closes, pos, fee_rate=D("0.0012"), entropy=D("0.4"))
    assert len(scores) == 3
    assert {s.name for s in scores} == {"up", "down", "flat"}


def test_gravity_well_does_not_force_trade() -> None:
    stagnant, advice = gravity_well_escape_optimizer(
        consecutive_holds=50, entropy=D("0.8"), has_position=False
    )
    assert stagnant is True
    assert "force" not in advice or "do not force" in advice


def test_anneal_multiplier_at_least_one() -> None:
    assert adaptive_basin_hopping(D("0.0024"), D("0.5")) >= D("1")


def test_guard_blocks_kill_and_pending() -> None:
    sig = Signal("BUY1", "buy", D("0.03"), "setup")
    ok, reason = self_healing_execution_guard(
        sig, pending=True, kill_switch=False, may_place_live=False, dry_run=True, amount_ok=True
    )
    assert ok is False
    assert reason == "pending_order"
    ok2, reason2 = self_healing_execution_guard(
        sig, pending=False, kill_switch=True, may_place_live=False, dry_run=True, amount_ok=True
    )
    assert ok2 is False
    assert reason2 == "kill_switch"


def test_build_quantum_view() -> None:
    view = build_quantum_view(
        [D(100 + i) for i in range(12)],
        None,
        Signal.hold("no_buy_setup"),
        entropy=D("0.3"),
        fee_rate=D("0.0012"),
        mark=D("110"),
        consecutive_holds=3,
        pending=False,
        kill_switch=False,
        may_place_live=False,
        dry_run=True,
    )
    assert view.guard_ok is False
    assert view.guard_reason == "no_side"
    assert len(view.scenarios) == 3
