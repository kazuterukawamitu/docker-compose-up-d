"""Unified signal → gate → Bitbank order path.

Strategies must not call the private order API. They return SignalCandidate
values; this module aggregates, gates, and delegates to OrderExecutor.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Sequence

from bitbank_bot.amounts import AmountPlan
from bitbank_bot.config import Config
from bitbank_bot.execution_gate import evaluate_gate
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO
from bitbank_bot.orders import OrderExecutor, OrderResult
from bitbank_bot.strategy import MarketSnapshot, Signal


@dataclass
class SignalCandidate:
    side: str
    trigger_price: Decimal
    current_price: Decimal
    strategy: str
    score: float
    reason: str
    signal: Signal
    previous_price: Decimal | None = None

    @classmethod
    def from_signal(cls, signal: Signal, snap: MarketSnapshot) -> "SignalCandidate":
        trigger = signal.cross_price or signal.origin_price or snap.close
        return cls(
            side=(signal.side or "HOLD").upper(),
            trigger_price=D(trigger),
            current_price=snap.close,
            strategy=signal.kind,
            score=float(signal.score),
            reason=signal.reason,
            signal=signal,
            previous_price=snap.prev_close,
        )


@dataclass
class CrossEvent:
    kind: str
    trigger_price: Decimal
    previous_price: Decimal
    current_price: Decimal


def detect_cross(
    previous_price: Decimal, current_price: Decimal, trigger_price: Decimal
) -> list[CrossEvent]:
    events: list[CrossEvent] = []
    if previous_price < trigger_price <= current_price:
        events.append(CrossEvent("cross_up", trigger_price, previous_price, current_price))
    if previous_price > trigger_price >= current_price:
        events.append(CrossEvent("cross_down", trigger_price, previous_price, current_price))
    return events


class SignalAggregator:
    def decide(
        self,
        candidates: Sequence[SignalCandidate],
        *,
        in_position: bool,
    ) -> Signal:
        buys = [c for c in candidates if c.side == "BUY"]
        sells = [c for c in candidates if c.side == "SELL"]
        if buys and sells:
            if in_position:
                best = max(sells, key=lambda c: c.score)
                slog("STRATEGY", "BUY/SELL conflict; prefer SELL in position", strategy=best.strategy)
                return best.signal
            slog("STRATEGY", "BUY/SELL conflict; HOLD", buy=buys[0].strategy, sell=sells[0].strategy)
            return Signal.hold("conflicting_buy_sell")
        actionable = sells or buys
        if not actionable:
            if candidates:
                return candidates[-1].signal
            return Signal.hold("no_candidates")
        best = max(actionable, key=lambda c: (c.score, c.current_price))
        return best.signal


@dataclass
class MarketScanner:
    last_close: Decimal | None = None

    def collect_levels(self, snap: MarketSnapshot, signal: Signal) -> dict[str, Decimal]:
        levels: dict[str, Decimal] = {"current": snap.close, "ma": snap.ma}
        if signal.cross_price is not None:
            levels["cross"] = signal.cross_price
        if signal.origin_price is not None:
            levels["origin"] = signal.origin_price
        if signal.peak_price is not None:
            levels["peak"] = signal.peak_price
        self.last_close = snap.close
        return levels


class FillTracker:
    def __init__(self) -> None:
        self.by_id: dict[str, OrderResult] = {}

    def record(self, result: OrderResult) -> None:
        if result.order_id:
            self.by_id[result.order_id] = result


@dataclass
class TradePipeline:
    cfg: Config
    executor: OrderExecutor
    aggregator: SignalAggregator = field(default_factory=SignalAggregator)
    scanner: MarketScanner = field(default_factory=MarketScanner)
    fills: FillTracker = field(default_factory=FillTracker)
    last_order_side: str | None = None
    last_order_mono: float = 0.0
    order_in_flight: bool = False

    def request_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def submit(
        self,
        signal: Signal,
        plan: AmountPlan,
        *,
        market_data_real: bool,
        market_data_fresh: bool,
        private_api_ok: bool,
        kill_switch: bool,
        duplicate_order: bool,
        cooldown: bool,
        open_order_conflict: bool,
        connection_ok: bool,
        atr_ok: bool,
        explicit_synthetic: bool,
        extra_candidates: Iterable[SignalCandidate] = (),
        snap: MarketSnapshot | None = None,
        in_position: bool = False,
    ) -> OrderResult:
        request_id = self.request_id()
        candidates = list(extra_candidates)
        if snap is not None:
            candidates.append(SignalCandidate.from_signal(signal, snap))
            self.scanner.collect_levels(snap, signal)
        if candidates:
            signal = self.aggregator.decide(candidates, in_position=in_position)
        slog(
            "SIGNAL_CREATED",
            "signal",
            request_id=request_id,
            pair=self.cfg.pair,
            kind=signal.kind,
            side=signal.side,
            reason=signal.reason,
            score=signal.score,
            signal_strength=signal.score,
        )
        if signal.side not in {"buy", "sell"}:
            slog("STRATEGY", "HOLD after aggregate", reason=signal.reason, request_id=request_id)
            return OrderResult(
                False, f"HOLD/{signal.reason}", self.cfg.dry_run, False, None, None, ZERO, ZERO, None, None
            )
        gate = evaluate_gate(
            cfg=self.cfg,
            signal=signal,
            market_data_real=market_data_real,
            market_data_fresh=market_data_fresh,
            private_api_ok=private_api_ok,
            balance_ok=plan.ok,
            amount=plan.amount,
            kill_switch=kill_switch,
            duplicate_order=duplicate_order or self.order_in_flight,
            cooldown=cooldown,
            open_order_conflict=open_order_conflict,
            connection_ok=connection_ok,
            atr_ok=atr_ok,
            explicit_synthetic=explicit_synthetic,
        )
        if not gate.allowed:
            return OrderResult(
                False,
                f"BLOCKED/{gate.reason}",
                self.cfg.dry_run,
                False,
                None,
                None,
                ZERO,
                ZERO,
                None,
                None,
            )
        slog(
            "ORDER_REQUESTED",
            "pipeline submit",
            request_id=request_id,
            pair=self.cfg.pair,
            side=plan.side,
            amount=str(plan.amount),
            price=str(plan.price),
            strategy=signal.kind,
        )
        self.order_in_flight = True
        try:
            result = self.executor.place(signal, plan, request_id=request_id)
        finally:
            self.order_in_flight = False
        self.last_order_side = plan.side
        self.fills.record(result)
        return result


def submit_order(
    cfg: Config,
    executor: OrderExecutor,
    signal: Signal,
    plan: AmountPlan,
    **kwargs: object,
) -> OrderResult:
    """Single live-order entry used by the engine."""
    pipeline = TradePipeline(cfg, executor)
    return pipeline.submit(signal, plan, **kwargs)  # type: ignore[arg-type]
