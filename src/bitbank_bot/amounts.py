"""PositionSizer: the only place that sets order quantity.

Strategy must not choose size. Recalculate from free_amount every order.
Never treat TARGET/PLANNED as a fill — those fields are telemetry only.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
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


def _risk_size_btc(
    *,
    available_jpy: Decimal,
    available_btc: Decimal,
    price: Decimal,
    cfg: Config,
    risk_pct: Decimal | None,
    sl_pct: Decimal | None,
    size_mult: Decimal,
) -> Decimal | None:
    if risk_pct is None or sl_pct is None or sl_pct <= ZERO or risk_pct <= ZERO:
        return None
    equity = available_jpy + available_btc * price
    if equity <= ZERO:
        return None
    capped_risk = min(D(risk_pct), cfg.max_risk_per_trade, cfg.max_risk_pct)
    if capped_risk < cfg.min_risk_pct:
        capped_risk = cfg.min_risk_pct
    risk_jpy = equity * capped_risk
    loss_per_btc = price * D(sl_pct)
    if loss_per_btc <= ZERO:
        return None
    raw = (risk_jpy / loss_per_btc) * D(size_mult)
    slog(
        "POSITION_SIZE_CALCULATED",
        "risk-based size",
        equity=str(equity),
        risk_jpy=str(risk_jpy),
        loss_per_btc=str(loss_per_btc),
        raw_btc=str(raw),
    )
    return raw


def plan_buy(
    *,
    available_jpy: Decimal,
    available_btc: Decimal,
    price: Decimal,
    cfg: Config,
    risk: RiskManager,
    target_jpy: Decimal | None = None,
    risk_pct: Decimal | None = None,
    sl_pct: Decimal | None = None,
    size_mult: Decimal | None = None,
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
    sized = _risk_size_btc(
        available_jpy=available_jpy,
        available_btc=available_btc,
        price=price,
        cfg=cfg,
        risk_pct=risk_pct,
        sl_pct=sl_pct,
        size_mult=size_mult if size_mult is not None else ONE,
    )
    if sized is not None:
        balance_btc = min(balance_btc, sized)
    decision = risk.check_buy(available_btc, balance_btc)
    raw = min(balance_btc, decision.capped_btc) if decision.allowed else ZERO
    amount = truncate(raw, cfg.amount_precision)
    planned = amount * price
    ok = decision.allowed and meets_min_amount(amount, cfg.min_amount_btc)
    if ok:
        reason = "ok"
        slog("POSITION_SIZE_CALCULATED", "buy size", amount=str(amount), planned_order_jpy=str(planned))
    elif not decision.allowed:
        reason = decision.reason
        slog("ORDER_BLOCKED", "buy blocked", reason=reason, side="buy")
    elif amount > ZERO:
        reason = "amount_below_minimum"
        slog("ORDER_BLOCKED", "buy blocked", reason=reason, amount=str(amount))
    else:
        reason = "insufficient"
        slog("ORDER_BLOCKED", "buy blocked", reason=reason, side="buy")
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
        slog("ORDER_BLOCKED", "sell blocked", reason=reason, side="sell")
    elif amount > ZERO:
        reason = "amount_below_minimum"
        slog("ORDER_BLOCKED", "sell blocked", reason=reason, amount=str(amount))
    else:
        reason = "insufficient"
        slog("ORDER_BLOCKED", "sell blocked", reason=reason, side="sell")
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
        risk_pct: Decimal | None = None,
        sl_pct: Decimal | None = None,
        size_mult: Decimal | None = None,
    ) -> AmountPlan:
        return plan_buy(
            available_jpy=available_jpy,
            available_btc=available_btc,
            price=price,
            cfg=self.cfg,
            risk=self.risk,
            target_jpy=target_jpy,
            risk_pct=risk_pct,
            sl_pct=sl_pct,
            size_mult=size_mult,
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
