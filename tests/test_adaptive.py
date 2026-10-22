from __future__ import annotations

from decimal import Decimal

from bitbank_bot.adaptive import (
    adaptive_basin_hopping,
    gravity_well_escape_optimizer,
    multi_scenario_inference,
    probability_state_updater,
    self_healing_execution_guard,
    shannon_entropy,
    spline_end_slope,
)
from bitbank_bot.money import D


def test_entropy_and_posterior_stay_open_without_history() -> None:
    assert shannon_entropy([]) == 0
    posterior = probability_state_updater([])
    assert posterior["down"] == posterior["up"] == posterior["flat"]
    allowed, reason = self_healing_execution_guard(
        side="buy",
        kind="BUY1",
        tp_pct=D("0.03"),
        fee_rate=D("0.0012"),
        entropy=D("1.58"),
        samples=0,
        posterior_down=D("0.9"),
        daily_halt=False,
    )
    assert allowed is True
    assert reason == "ok"


def test_guard_blocks_fee_entropy_and_posterior_only_after_samples() -> None:
    fee_ok, fee_reason = self_healing_execution_guard(
        side="buy",
        kind="BUY1",
        tp_pct=D("0.001"),
        fee_rate=D("0.0012"),
        entropy=D("0"),
        samples=0,
        posterior_down=D("0.33"),
        daily_halt=False,
    )
    assert fee_ok is False
    assert fee_reason == "fee_edge"
    mixed = [D("0.01"), D("-0.01"), D("0")] * 3
    blocked, why = self_healing_execution_guard(
        side="buy",
        kind="BUY1",
        tp_pct=D("0.03"),
        fee_rate=D("0.0012"),
        entropy=shannon_entropy(mixed),
        samples=len(mixed),
        posterior_down=probability_state_updater(mixed)["down"],
        daily_halt=False,
    )
    assert blocked is False
    assert why == "entropy"
    down = [D("-0.01")] * 8
    blocked, why = self_healing_execution_guard(
        side="buy",
        kind="BUY1",
        tp_pct=D("0.03"),
        fee_rate=D("0.0012"),
        entropy=shannon_entropy(down),
        samples=8,
        posterior_down=probability_state_updater(down)["down"],
        daily_halt=False,
    )
    assert blocked is False
    assert why == "posterior_down"
    sell_ok, sell_reason = self_healing_execution_guard(
        side="sell",
        kind="STOP",
        tp_pct=D("0.001"),
        fee_rate=D("0.0012"),
        entropy=D("1.58"),
        samples=8,
        posterior_down=D("0.9"),
        daily_halt=True,
    )
    assert sell_ok is True
    assert sell_reason == "exit_allowed"


def test_hold_optimizer_and_scenarios_do_not_order() -> None:
    text = gravity_well_escape_optimizer(
        in_position=True, signal_kind="HOLD", block_reason="", samples=1
    )
    assert text.startswith("hold:")
    assert "position_open_wait_exit_rule" in text
    scenarios = multi_scenario_inference(D("0.001"), D("10000000"), D("0.0012"))
    assert set(scenarios) == {"bull", "flat", "bear"}
    assert scenarios["bull"] > scenarios["flat"] > scenarios["bear"]
    assert scenarios["flat"] < 0


def test_spline_slope_of_a_line_is_one() -> None:
    slope = spline_end_slope([D(str(i)) for i in range(6)])
    assert abs(slope - D("1")) < D("0.0001")


def test_basin_hop_stays_a_suggestion() -> None:
    suggested = adaptive_basin_hopping(
        [D("100"), D("100"), D("101")], D("0.0005")
    )
    assert isinstance(suggested, Decimal)
