"""Ordinary diagnostics named after the requested ideas.

These functions do not run a quantum computer, do not place orders, and do not
change the live moving-average slope. High entropy or a down posterior can only
block a new buy after enough samples.
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Sequence

from bitbank_bot.fees import fee_allows_target, round_trip_cost_rate
from bitbank_bot.money import D, ONE, ZERO

ENTROPY_MIN_SAMPLES = 8
ENTROPY_BLOCK = D("1.50")
POSTERIOR_DOWN_BLOCK = D("0.55")
RETURN_BIN = D("0.001")


def _bins(returns: Sequence[Decimal]) -> tuple[int, int, int]:
    down = flat = up = 0
    for raw in returns:
        value = D(raw)
        if value < -RETURN_BIN:
            down += 1
        elif value > RETURN_BIN:
            up += 1
        else:
            flat += 1
    return down, flat, up


def shannon_entropy(returns: Sequence[Decimal]) -> Decimal:
    """Shannon entropy in bits of a 3-bin return histogram. Max is log2(3)."""
    down, flat, up = _bins(returns)
    total = down + flat + up
    if total <= 0:
        return ZERO
    entropy = 0.0
    for count in (down, flat, up):
        if count <= 0:
            continue
        p = count / total
        entropy -= p * math.log2(p)
    return D(str(entropy))


def probability_state_updater(returns: Sequence[Decimal]) -> dict[str, Decimal]:
    """Laplace-smoothed posterior over down / flat / up. Empty history is uniform."""
    down, flat, up = _bins(returns)
    down_w = Decimal(down + 1)
    flat_w = Decimal(flat + 1)
    up_w = Decimal(up + 1)
    total = down_w + flat_w + up_w
    return {"down": down_w / total, "flat": flat_w / total, "up": up_w / total}


def gravity_well_escape_optimizer(
    *,
    in_position: bool,
    signal_kind: str,
    block_reason: str,
    samples: int,
) -> str:
    """Explain a HOLD. This returns text and never an order."""
    if signal_kind not in {"", "HOLD"} and not block_reason:
        return "not_holding"
    parts: list[str] = []
    if block_reason:
        parts.append(f"blocked:{block_reason}")
    parts.append("position_open_wait_exit_rule" if in_position else "no_granville_setup")
    if samples < ENTROPY_MIN_SAMPLES:
        parts.append("entropy_warmup")
    return "hold:" + ",".join(parts)


def adaptive_basin_hopping(closes: Sequence[Decimal], start_slope: Decimal) -> Decimal:
    """Eight cheap slope guesses. Offline only; the live MA slope is not written."""
    start = D(start_slope)
    if len(closes) < 3:
        return start
    prev = D(closes[-2])
    if prev <= ZERO:
        return start
    realized = (D(closes[-1]) - prev) / prev
    best = start
    best_err = abs(best - realized)
    step = D("0.0001")
    for i in range(8):
        candidate = start + step * Decimal(i - 4)
        err = abs(candidate - realized)
        if err < best_err:
            best = candidate
            best_err = err
    return best


def _scenario_pnl(amount: Decimal, price: Decimal, move: Decimal, fee_rate: Decimal) -> Decimal:
    entry = amount * price
    exit_price = price * (ONE + move)
    gross = amount * exit_price
    fees = (entry + gross) * fee_rate
    return gross - entry - fees


def multi_scenario_inference(
    amount: Decimal,
    price: Decimal,
    fee_rate: Decimal,
) -> dict[str, Decimal]:
    """Fee-adjusted bull / flat / bear results. No orders are submitted."""
    amount = D(amount)
    price = D(price)
    fee_rate = D(fee_rate)
    if amount <= ZERO:
        amount = D("0.001")
    moves = {"bull": D("0.01"), "flat": ZERO, "bear": D("-0.01")}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            name: pool.submit(_scenario_pnl, amount, price, move, fee_rate)
            for name, move in moves.items()
        }
        return {name: futures[name].result() for name in moves}


def spline_end_slope(values: Sequence[Decimal]) -> Decimal:
    """End slope of a natural cubic spline through equally spaced points."""
    ys = [D(v) for v in values]
    n = len(ys)
    if n < 4:
        if n >= 2:
            return ys[-1] - ys[-2]
        return ZERO
    size = n - 2
    rhs = [6 * (ys[i + 1] - 2 * ys[i] + ys[i - 1]) for i in range(1, n - 1)]
    carry_c = [ZERO] * size
    carry_d = [ZERO] * size
    carry_c[0] = D(1) / D(4)
    carry_d[0] = rhs[0] / D(4)
    for i in range(1, size):
        upper = ZERO if i == size - 1 else ONE
        denom = D(4) - carry_c[i - 1]
        carry_c[i] = upper / denom
        carry_d[i] = (rhs[i] - carry_d[i - 1]) / denom
    second = [ZERO] * n
    second[n - 2] = carry_d[-1]
    for i in range(size - 2, -1, -1):
        second[i + 1] = carry_d[i] - carry_c[i] * second[i + 2]
    return (ys[-1] - ys[-2]) - second[n - 2] / D(6)


def self_healing_execution_guard(
    *,
    side: str,
    kind: str,
    tp_pct: Decimal | None,
    fee_rate: Decimal,
    entropy: Decimal,
    samples: int,
    posterior_down: Decimal,
    daily_halt: bool,
) -> tuple[bool, str]:
    """Allow exits. Block a buy only for a fee gap, a daily halt, or a warmed-up signal."""
    if side != "buy":
        return True, "exit_allowed"
    if kind in {"STOP", "TP", "SELL1", "SELL2", "SELL3", "SELL4"}:
        return True, "exit_allowed"
    if daily_halt:
        return False, "daily_halt"
    target = D(tp_pct) if tp_pct is not None else ZERO
    if not fee_allows_target(target, round_trip_cost_rate(fee_rate)):
        return False, "fee_edge"
    if samples >= ENTROPY_MIN_SAMPLES and D(entropy) >= ENTROPY_BLOCK:
        return False, "entropy"
    if samples >= ENTROPY_MIN_SAMPLES and D(posterior_down) >= POSTERIOR_DOWN_BLOCK:
        return False, "posterior_down"
    return True, "ok"
