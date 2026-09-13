"""Single path from strategy signal to Bitbank order (or WOULD_SUBMIT_ORDER).

MarketScanner / SignalAggregator / TradeGate live here so strategy modules
never call the private order API. OrderExecutor remains the only create_order
caller.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Sequence

from bitbank_bot.amounts import AmountPlan, PositionSizer
from bitbank_bot.config import Config
from bitbank_bot.execution_gate import ExecutionGate, GateContext
from bitbank_bot.logging_setup import slog
from bitbank_bot.market_data import Candle
from bitbank_bot.money import ZERO
from bitbank_bot.orders import OrderExecutor, OrderResult
from bitbank_bot.rate_engine import RateDecision, RateEngine
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import Signal


@dataclass
class SignalCandidate:
    side: str
    trigger_price: Decimal | None
    current_price: Decimal
    strategy: str
    score: float
    reason: str


@dataclass
class SubmitOutcome:
    result: OrderResult | None
    plan: AmountPlan | None
    rate: RateDecision | None
    blocked: str
    trace_id: str


class SignalAggregator:
    def choose(self, candidates: list[SignalCandidate], fallback: Signal) -> Signal:
        buys = [c for c in candidates if c.side == "BUY"]
        sells = [c for c in candidates if c.side == "SELL"]
        if buys and sells:
            slog("STRATEGY", "BUY/SELL conflict; SELL wins", buy=len(buys), sell=len(sells))
            best = max(sells, key=lambda c: c.score)
            return Signal(best.strategy, "sell", fallback.tp_pct, best.reason)
        if sells:
            best = max(sells, key=lambda c: c.score)
            return Signal(best.strategy, "sell", fallback.tp_pct, best.reason)
        if buys:
            best = max(buys, key=lambda c: c.score)
            return Signal(best.strategy, "buy", fallback.tp_pct, best.reason)
        return fallback


class TradeSignalExecutor:
    def __init__(
        self,
        cfg: Config,
        risk: RiskManager,
        order_client: Any | None,
    ) -> None:
        self.cfg = cfg
        self.risk = risk
        self.sizer = PositionSizer(cfg, risk)
        self.gate = ExecutionGate(cfg)
        self.rates = RateEngine(cfg)
        self.orders = OrderExecutor(cfg, order_client)
        self.last_order_mono = 0.0
        self.last_order_side = ""

    def submit(
        self,
        signal: Signal,
        *,
        price: Decimal,
        candles: Sequence[Candle],
        available_jpy: Decimal,
        available_btc: Decimal,
        market_data_real: bool,
        market_data_fresh: bool,
        private_api_ok: bool,
        pending_order: bool,
        kill_switch: bool,
        ws_stale: bool,
        explicit_synthetic: bool,
        extra_reason: str = "",
    ) -> SubmitOutcome:
        trace_id = uuid.uuid4().hex[:12]
        slog(
            "SIGNAL_CREATED",
            "signal ready for execution path",
            trace_id=trace_id,
            kind=signal.kind,
            side=signal.side,
            reason=signal.reason,
            price=str(price),
        )
        rate = self.rates.decide(signal, candles, price=price)
        if signal.side == "buy" and signal.tp_pct is None:
            signal.tp_pct = rate.take_profit_pct
        elif signal.side == "buy" and rate.mode == "dynamic" and rate.ok:
            signal.tp_pct = rate.take_profit_pct

        cooldown = False
        remaining = 0.0
        if self.cfg.cooldown_seconds > 0 and self.last_order_mono > 0:
            elapsed = time.monotonic() - self.last_order_mono
            remaining = self.cfg.cooldown_seconds - elapsed
            cooldown = remaining > 0
            slog(
                "HEARTBEAT",
                "cooldown",
                cooldown_active=cooldown,
                cooldown_seconds=self.cfg.cooldown_seconds,
                elapsed_seconds=round(elapsed, 3),
                remaining_seconds=round(max(0.0, remaining), 3),
            )

        open_conflict = False
        if self.cfg.has_keys and self.cfg.resolved_trading_mode() in {"live", "live_ready"}:
            try:
                active = self.orders.active_orders()
                open_conflict = len(active) > 0
                if open_conflict:
                    first = active[0]
                    slog(
                        "ORDER_STATUS",
                        "active orders present",
                        count=len(active),
                        order_id=str(first.get("order_id") or ""),
                        side=first.get("side"),
                        status=first.get("status"),
                    )
            except Exception as exc:
                slog("ERROR", "active_orders failed before gate", error=type(exc).__name__)
                extra_reason = extra_reason or "active_orders_unreadable"

        if signal.side == "buy":
            plan = self.sizer.plan_buy(
                available_jpy=available_jpy,
                available_btc=available_btc,
                price=price,
                rate=rate,
            )
        else:
            plan = self.sizer.plan_sell(
                available_jpy=available_jpy,
                available_btc=available_btc,
                price=price,
            )
        slog(
            "POSITION_SIZE_CALCULATED",
            plan.reason,
            amount=str(plan.amount),
            planned_order_jpy=str(plan.planned_order_jpy),
            rate_mode=rate.mode,
        )

        ctx = GateContext(
            signal=signal,
            market_data_real=market_data_real,
            market_data_fresh=market_data_fresh,
            private_api_ok=private_api_ok,
            balance_ok=available_jpy > ZERO or available_btc > ZERO,
            amount_ok=plan.ok,
            amount=plan.amount,
            kill_switch=kill_switch,
            pending_order=pending_order,
            cooldown_active=cooldown,
            open_order_conflict=open_conflict,
            ws_stale=ws_stale,
            explicit_synthetic=explicit_synthetic,
            rate=rate,
            extra_reason=extra_reason,
        )
        decision = self.gate.evaluate(ctx)
        if not decision.allowed:
            slog(
                "TRADE_BLOCKED",
                "execution not reached",
                reason=decision.reason,
                trace_id=trace_id,
            )
            return SubmitOutcome(None, plan, rate, decision.reason, trace_id)

        if self.cfg.signal_only:
            slog("EXECUTION_BLOCKED", "SIGNAL_ONLY", trace_id=trace_id)
            return SubmitOutcome(None, plan, rate, "signal_only", trace_id)

        slog(
            "ORDER_REQUESTED",
            "submitting to OrderExecutor",
            trace_id=trace_id,
            side=plan.side,
            amount=str(plan.amount),
            price=str(plan.price),
        )
        result = self.orders.place(signal, plan)
        if result.ok and (result.order_id or result.simulated or result.reason == "would_submit"):
            self.last_order_mono = time.monotonic()
            self.last_order_side = plan.side
        return SubmitOutcome(result, plan, rate, "", trace_id)


def crossed_above(previous: Decimal, current: Decimal, trigger: Decimal) -> bool:
    return previous < trigger <= current


def crossed_below(previous: Decimal, current: Decimal, trigger: Decimal) -> bool:
    return previous > trigger >= current
