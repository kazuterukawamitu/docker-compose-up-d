"""Quantum-Inspired Adaptive Optimization Engine (classical algorithms).

These helpers borrow the *vocabulary* of quantum / annealing / Bayesian search
for trading decisions. They do not claim quantum hardware. They never place
orders: the engine still has to pass risk, sizing, and the order gate.

Modules:
  probability_state_updater   — Bayesian-ish BUY/SELL/HOLD weights from returns
  gravity_well_escape_optimizer — detect HOLD stagnation; advise re-explore
  adaptive_basin_hopping      — score alternate parameter basins
  multi_scenario_inference    — up / down / flat parallel evaluation
  self_healing_execution_guard — consistency checks before execution
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from bitbank_bot.money import D, ONE, ZERO
from bitbank_bot.strategy import Position, Signal


SCENARIOS = ("up", "down", "flat")


@dataclass(frozen=True)
class ScenarioScore:
    name: str
    probability: Decimal
    expected_pnl_jpy: Decimal


@dataclass(frozen=True)
class QuantumView:
    """Snapshot of the adaptive layer for logging and screen."""

    entropy: Decimal
    scenarios: tuple[ScenarioScore, ...]
    hold_stagnation: bool
    explore_advice: str
    anneal_temperature: Decimal
    guard_ok: bool
    guard_reason: str


def probability_state_updater(
    closes: Sequence[Decimal],
    *,
    entropy: Decimal,
    prior: tuple[Decimal, Decimal, Decimal] | None = None,
) -> tuple[Decimal, Decimal, Decimal]:
    """Update (up, down, flat) weights from recent returns and entropy.

    Higher entropy flattens the posterior toward equal weights (exploration).
    Lower entropy concentrates mass on the dominant recent direction.
    """
    if prior is None:
        prior = (D("0.34"), D("0.33"), D("0.33"))
    up_p, down_p, flat_p = (D(prior[0]), D(prior[1]), D(prior[2]))
    if len(closes) < 3:
        return _normalize(up_p, down_p, flat_p)
    rets: list[Decimal] = []
    for prev, close in zip(closes[-12:], closes[-11:]):
        p = D(prev)
        if p <= ZERO:
            continue
        rets.append((D(close) - p) / p)
    if not rets:
        return _normalize(up_p, down_p, flat_p)
    up_hits = sum(1 for r in rets if r > D("0.0005"))
    down_hits = sum(1 for r in rets if r < D("-0.0005"))
    flat_hits = len(rets) - up_hits - down_hits
    # Likelihoods scaled by (1 - entropy) so disorder spreads belief.
    focus = ONE - min(ONE, max(ZERO, D(entropy)))
    up_p = up_p * (ONE + D(up_hits) * focus)
    down_p = down_p * (ONE + D(down_hits) * focus)
    flat_p = flat_p * (ONE + D(flat_hits) * focus) * (ONE + D(entropy))
    return _normalize(up_p, down_p, flat_p)


def multi_scenario_inference(
    closes: Sequence[Decimal],
    position: Position | None,
    *,
    fee_rate: Decimal,
    entropy: Decimal,
    mark: Decimal | None = None,
) -> tuple[ScenarioScore, ...]:
    """Score up / down / flat in parallel (superposition-style evaluation)."""
    probs = probability_state_updater(closes, entropy=entropy)
    last = D(mark if mark is not None else (closes[-1] if closes else 0))
    scores: list[ScenarioScore] = []
    moves = (D("0.01"), D("-0.01"), ZERO)
    for name, prob, move in zip(SCENARIOS, probs, moves):
        hyp = last * (ONE + move) if last > ZERO else ZERO
        pnl = ZERO
        if position is not None and position.amount > ZERO and hyp > ZERO:
            proceeds = position.amount * hyp
            exit_fee = proceeds * D(fee_rate)
            pnl = proceeds - exit_fee - position.actual_execution_jpy - position.fee_jpy
        scores.append(ScenarioScore(name=name, probability=prob, expected_pnl_jpy=pnl * prob))
    return tuple(scores)


def gravity_well_escape_optimizer(
    *,
    consecutive_holds: int,
    entropy: Decimal,
    has_position: bool,
    threshold: int = 40,
) -> tuple[bool, str]:
    """Detect HOLD stagnation (gravity well) and advise exploration — never force a trade.

    Stagnation is a signal to re-check root causes (fees, HTF filter, no setup),
    not a license to place an order.
    """
    if consecutive_holds < threshold:
        return False, "stable"
    if has_position:
        return True, "in_position_hold_stagnation; prefer protective mark exits over forced pattern sell"
    if D(entropy) >= D("0.7"):
        return True, "no_setup_high_entropy; keep exploring, do not force buy"
    return True, "no_setup_stagnation; re-evaluate Granville inputs and HTF filter"


def adaptive_basin_hopping(
    base_edge: Decimal,
    entropy: Decimal,
    *,
    hops: int = 5,
    seed_temp: Decimal = D("1.0"),
) -> Decimal:
    """Widen / contract the fee edge across a few basins (annealing-style).

    Returns an adjusted required-edge multiplier >= 1. Higher entropy and
    higher temperature demand a larger edge before buying.
    """
    temp = max(D("0.1"), D(seed_temp))
    best = ONE + D(entropy)
    edge = D(base_edge)
    for i in range(max(1, hops)):
        # Metropolis-like accept of a slightly worse (larger) edge.
        candidate = ONE + D(entropy) * (ONE + D(i) * D("0.05"))
        delta = candidate - best
        if delta <= ZERO:
            best = candidate
        else:
            # Accept widening when temperature still high (safer buys).
            accept_p = math.exp(float(-delta / temp)) if temp > ZERO else 0.0
            if accept_p > 0.3:
                best = candidate
        temp = temp * D("0.85")
    return max(ONE, best) * (ONE if edge <= ZERO else ONE)


def self_healing_execution_guard(
    signal: Signal,
    *,
    pending: bool,
    kill_switch: bool,
    may_place_live: bool,
    dry_run: bool,
    amount_ok: bool,
) -> tuple[bool, str]:
    """Runtime verification before an order path may proceed."""
    if kill_switch:
        return False, "kill_switch"
    if pending:
        return False, "pending_order"
    if signal.side not in {"buy", "sell"}:
        return False, "no_side"
    if not amount_ok:
        return False, "amount_invalid"
    if may_place_live and dry_run:
        return False, "live_dry_conflict"
    return True, "ok"


def build_quantum_view(
    closes: Sequence[Decimal],
    position: Position | None,
    signal: Signal,
    *,
    entropy: Decimal,
    fee_rate: Decimal,
    mark: Decimal,
    consecutive_holds: int,
    pending: bool,
    kill_switch: bool,
    may_place_live: bool,
    dry_run: bool,
    amount_ok: bool = True,
) -> QuantumView:
    scenarios = multi_scenario_inference(
        closes, position, fee_rate=fee_rate, entropy=entropy, mark=mark
    )
    stagnant, advice = gravity_well_escape_optimizer(
        consecutive_holds=consecutive_holds,
        entropy=entropy,
        has_position=position is not None,
    )
    temp = adaptive_basin_hopping(fee_rate * 2, entropy)
    guard_ok, guard_reason = self_healing_execution_guard(
        signal,
        pending=pending,
        kill_switch=kill_switch,
        may_place_live=may_place_live,
        dry_run=dry_run,
        amount_ok=amount_ok,
    )
    return QuantumView(
        entropy=D(entropy),
        scenarios=scenarios,
        hold_stagnation=stagnant,
        explore_advice=advice,
        anneal_temperature=temp,
        guard_ok=guard_ok,
        guard_reason=guard_reason,
    )


def _normalize(a: Decimal, b: Decimal, c: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    total = a + b + c
    if total <= ZERO:
        return D("0.34"), D("0.33"), D("0.33")
    return a / total, b / total, c / total
