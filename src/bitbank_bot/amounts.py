"""PositionSizer: the only place that sets order quantity.

Strategy must not choose size. Recalculate from free_amount every order.
Never treat TARGET/PLANNED as a fill — those fields are telemetry only.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from bitbank_bot.config import Config
from bitbank_bot.money import D, ONE, ZERO, meets_min_amount, truncate
from bitbank_bot.risk import RiskManager


@dataclass
class AmountPlan:
    side: str
    amount: Decimal
    price: Decimal
    available_jpy: Decimal
    available_btc: Decimal
    target_jpy: Decimal
    planned_order_jpy: Decimal
    actual_execution_jpy: Decimal | None
    actual_balance_jpy: Decimal
    actual_balance_btc: Decimal
    ok: bool
    reason: str


def plan_buy(
    *,
    available_jpy: Decimal,
    available_btc: Decimal,
    price: Decimal,
    cfg: Config,
    risk: RiskManager,
    target_jpy: Decimal | None = None,
) -> AmountPlan:
    available_jpy = D(available_jpy)
    available_btc = D(available_btc)
    price = D(price)
    if price <= ZERO:
        return AmountPlan(
            side="buy",
            amount=ZERO,
            price=price,
            available_jpy=available_jpy,
            available_btc=available_btc,
            target_jpy=ZERO,
            planned_order_jpy=ZERO,
            actual_execution_jpy=None,
            actual_balance_jpy=available_jpy,
            actual_balance_btc=available_btc,
            ok=False,
            reason="invalid_price",
        )
    max_usable_jpy = available_jpy * cfg.max_balance_usage * (ONE - cfg.fee_buffer)
    if target_jpy is None:
        target_jpy = max_usable_jpy
    else:
        target_jpy = D(target_jpy)
    usable_jpy = min(target_jpy, max_usable_jpy)
    balance_btc = usable_jpy / price
    decision = risk.check_buy(available_btc, balance_btc)
    raw = min(balance_btc, decision.capped_btc) if decision.allowed else ZERO
    amount = truncate(raw, cfg.amount_precision)
    planned = amount * price
    ok = decision.allowed and meets_min_amount(amount, cfg.min_amount_btc)
    if ok:
        reason = "ok"
    elif not decision.allowed:
        reason = decision.reason
    elif amount > ZERO:
        reason = "below_min_amount"
    else:
        reason = "insufficient"
    return AmountPlan(
        side="buy",
        amount=amount if ok else ZERO,
        price=price,
        available_jpy=available_jpy,
        available_btc=available_btc,
        target_jpy=target_jpy,
        planned_order_jpy=planned if ok else ZERO,
        actual_execution_jpy=None,
        actual_balance_jpy=available_jpy,
        actual_balance_btc=available_btc,
        ok=ok,
        reason=reason,
    )


def plan_sell(
    *,
    available_jpy: Decimal,
    available_btc: Decimal,
    price: Decimal,
    cfg: Config,
    risk: RiskManager,
) -> AmountPlan:
    available_jpy = D(available_jpy)
    available_btc = D(available_btc)
    price = D(price)
    target_jpy = available_btc * price
    raw = available_btc * cfg.sell_safety_factor
    decision = risk.check_sell(raw)
    raw = min(raw, decision.capped_btc) if decision.allowed else ZERO
    amount = truncate(raw, cfg.amount_precision)
    leftover = available_btc - amount
    if ZERO < leftover <= cfg.min_amount_btc:
        amount = truncate(available_btc, cfg.amount_precision)
    planned = amount * price
    ok = decision.allowed and meets_min_amount(amount, cfg.min_amount_btc)
    if ok:
        reason = "ok"
    elif not decision.allowed:
        reason = decision.reason
    elif amount > ZERO:
        reason = "below_min_amount"
    else:
        reason = "insufficient"
    return AmountPlan(
        side="sell",
        amount=amount if ok else ZERO,
        price=price,
        available_jpy=available_jpy,
        available_btc=available_btc,
        target_jpy=target_jpy,
        planned_order_jpy=planned if ok else ZERO,
        actual_execution_jpy=None,
        actual_balance_jpy=available_jpy,
        actual_balance_btc=available_btc,
        ok=ok,
        reason=reason,
    )


class PositionSizer:
    """Single quantity calculator. Strategy must not set size."""

    def __init__(self, cfg: Config, risk: RiskManager) -> None:
        self.cfg = cfg
        self.risk = risk

    def plan_buy(
        self,
        *,
        available_jpy: Decimal,
        available_btc: Decimal,
        price: Decimal,
        target_jpy: Decimal | None = None,
    ) -> AmountPlan:
        return plan_buy(
            available_jpy=available_jpy,
            available_btc=available_btc,
            price=price,
            cfg=self.cfg,
            risk=self.risk,
            target_jpy=target_jpy,
        )

    def plan_sell(
        self,
        *,
        available_jpy: Decimal,
        available_btc: Decimal,
        price: Decimal,
    ) -> AmountPlan:
        return plan_sell(
            available_jpy=available_jpy,
            available_btc=available_btc,
            price=price,
            cfg=self.cfg,
            risk=self.risk,
        )
