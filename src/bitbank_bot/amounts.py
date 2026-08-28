"""Position sizing from free_amount (never onhand_amount)."""

from __future__ import annotations

from decimal import Decimal

from bitbank_bot.models import AmountKind, AmountPlan, PairConstraints
from bitbank_bot.money import floor_to_unit, jpy_tick, to_decimal


def plan_buy(
    *,
    free_jpy: Decimal,
    price: Decimal,
    max_balance_usage: Decimal,
    fee_buffer: Decimal,
    constraints: PairConstraints,
) -> AmountPlan:
    """BUY: free_jpy * MAX_BALANCE_USAGE / price, minus fee buffer, floored to unit."""
    free_jpy = to_decimal(free_jpy)
    price = jpy_tick(price, side="buy")
    if price <= 0:
        return AmountPlan(
            kind=AmountKind.PLANNED,
            side="buy",
            target_amount=Decimal("0"),
            planned_amount=Decimal("0"),
            price=price,
            quote_budget=free_jpy,
            reason="invalid_price",
            min_amount=constraints.min_amount,
            max_amount=constraints.limit_max_amount,
        )
    target_quote = free_jpy * max_balance_usage
    after_fee = target_quote * (Decimal("1") - fee_buffer)
    target_btc = after_fee / price
    planned = floor_to_unit(target_btc, constraints.unit_amount)
    cap = constraints.limit_max_amount
    if cap is not None and planned > cap:
        planned = floor_to_unit(cap, constraints.unit_amount)
    reason = "buy_max_from_free_jpy"
    if planned < constraints.min_amount:
        reason = (
            f"below_min_amount planned={planned} min={constraints.min_amount} "
            "exchange min/max not bypassed"
        )
        planned = Decimal("0")
    return AmountPlan(
        kind=AmountKind.PLANNED,
        side="buy",
        target_amount=floor_to_unit(target_btc, constraints.unit_amount),
        planned_amount=planned,
        price=price,
        quote_budget=after_fee,
        reason=reason,
        min_amount=constraints.min_amount,
        max_amount=cap,
    )


def plan_sell_all(
    *,
    free_btc: Decimal,
    price: Decimal,
    constraints: PairConstraints,
) -> AmountPlan:
    """SELL ALL: latest free BTC floored to unit. Never use onhand_amount."""
    free_btc = to_decimal(free_btc)
    price = jpy_tick(price, side="sell")
    planned = floor_to_unit(free_btc, constraints.unit_amount)
    cap = constraints.limit_max_amount
    if cap is not None and planned > cap:
        planned = floor_to_unit(cap, constraints.unit_amount)
    reason = "sell_all_from_free_btc"
    if planned < constraints.min_amount:
        reason = (
            f"below_min_amount planned={planned} min={constraints.min_amount} "
            "exchange min/max not bypassed"
        )
        planned = Decimal("0")
    return AmountPlan(
        kind=AmountKind.PLANNED,
        side="sell",
        target_amount=floor_to_unit(free_btc, constraints.unit_amount),
        planned_amount=planned,
        price=price,
        quote_budget=None,
        reason=reason,
        min_amount=constraints.min_amount,
        max_amount=cap,
    )


plan_sell = plan_sell_all


def apply_max_position(
    plan: AmountPlan,
    *,
    current_btc: Decimal,
    max_position_btc: Decimal | None,
    unit: Decimal,
) -> AmountPlan:
    if plan.side != "buy" or max_position_btc is None:
        return plan
    current_btc = to_decimal(current_btc)
    headroom = max_position_btc - current_btc
    if headroom <= 0:
        plan.planned_amount = Decimal("0")
        plan.reason = "max_position_reached"
        return plan
    capped = floor_to_unit(min(plan.planned_amount, headroom), unit)
    if capped < plan.min_amount:
        plan.planned_amount = Decimal("0")
        plan.reason = "max_position_headroom_below_min"
        return plan
    if capped < plan.planned_amount:
        plan.planned_amount = capped
        plan.reason = "capped_by_max_position"
    return plan
