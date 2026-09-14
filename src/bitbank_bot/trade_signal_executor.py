"""Unified TradeGate + order hand-off.

Strategies must not call Bitbank. This module is the only place Engine uses
to decide whether OrderExecutor.place may run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import uuid4

from bitbank_bot.amounts import AmountPlan
from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import ZERO
from bitbank_bot.rate_engine import RateDecision
from bitbank_bot.strategy import Signal


@dataclass
class GateResult:
    allowed: bool
    reason: str
    trace_id: str
    would_submit: bool = False
    live: bool = False
    fields: dict[str, Any] = field(default_factory=dict)


def new_trace_id() -> str:
    return uuid4().hex[:12]


def evaluate_gate(
    cfg: Config,
    signal: Signal,
    plan: AmountPlan,
    *,
    market_data_real: bool,
    market_data_fresh: bool,
    private_api_ok: bool,
    kill_switch: bool,
    pending_order: bool,
    open_order_count: int,
    rate: RateDecision | None = None,
    trace_id: str | None = None,
) -> GateResult:
    tid = trace_id or new_trace_id()
    live = cfg.may_place_live_orders
    would = cfg.is_live_ready

    def blocked(reason: str, **extra: Any) -> GateResult:
        slog(
            "TRADE_BLOCKED",
            "EXECUTION_BLOCKED",
            reason=reason,
            trace_id=tid,
            kind=signal.kind,
            side=signal.side,
            **extra,
        )
        return GateResult(False, reason, tid, would_submit=would, live=live, fields=extra)

    if signal.side not in {"buy", "sell"}:
        return blocked("signal_not_actionable", signal_kind=signal.kind)
    if kill_switch:
        return blocked("kill_switch")
    if not market_data_real:
        return blocked("synthetic_market_data")
    if not market_data_fresh:
        return blocked("stale_market_data")
    if pending_order:
        return blocked("pending_order")
    if open_order_count > 0:
        return blocked("active_orders", count=open_order_count)
    if rate is not None and rate.reason == "abnormal_atr":
        return blocked("abnormal_atr")
    if rate is not None and rate.size_mult <= ZERO:
        return blocked("rate_size_zero")
    if not plan.ok or plan.amount <= ZERO:
        return blocked(plan.reason or "amount_invalid", amount=str(plan.amount))
    if live and not private_api_ok:
        return blocked("private_api_unhealthy")
    if live and not cfg.live_trading_confirm and cfg.trading_mode == "live":
        return blocked("live_confirm_missing")

    slog(
        "RISK_CHECK_PASSED",
        "TradeGate pass",
        trace_id=tid,
        kind=signal.kind,
        side=signal.side,
        amount=str(plan.amount),
        price=str(plan.price),
        mode=cfg.trading_mode,
        live=live,
        would_submit=would,
    )
    return GateResult(True, "ok", tid, would_submit=would, live=live)


def log_would_submit(signal: Signal, plan: AmountPlan, trace_id: str) -> None:
    slog(
        "WOULD_SUBMIT_ORDER",
        "LIVE_READY: not calling Bitbank create_order",
        trace_id=trace_id,
        pair="btc_jpy",
        side=plan.side,
        amount=str(plan.amount),
        price=str(plan.price),
        kind=signal.kind,
    )


def log_checkpoint(stage: str, trace_id: str, **fields: Any) -> None:
    slog(stage, "checkpoint", trace_id=trace_id, **fields)
