"""Single path from a strategy signal to Bitbank (or a dry / LIVE_READY stand-in).

Strategy modules must not call the order API. They emit Signal; this module
runs RateEngine → ExecutionGate → PositionSizer → OrderExecutor.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Sequence

from bitbank_bot.amounts import AmountPlan, PositionSizer
from bitbank_bot.config import Config
from bitbank_bot.connection_manager import ConnectionSnapshot
from bitbank_bot.execution_gate import ExecutionGate, GateResult
from bitbank_bot.logging_setup import slog
from bitbank_bot.market_data import Candle
from bitbank_bot.money import D, ZERO
from bitbank_bot.orders import OrderExecutor, OrderResult
from bitbank_bot.rate_engine import RateDecision, RateEngine
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import Signal


@dataclass
class PipelineResult:
    signal: Signal
    rate: RateDecision | None
    plan: AmountPlan | None
    gate: GateResult | None
    order: OrderResult | None
    blocked: bool
    block_reason: str


class TradeSignalExecutor:
    def __init__(self, cfg: Config, client: Any | None) -> None:
        self.cfg = cfg
        self.client = client
        self.rate_engine = RateEngine(cfg)
        self.gate = ExecutionGate(cfg)
        self.orders = OrderExecutor(cfg, client)

    def run(
        self,
        *,
        signal: Signal,
        price: Decimal,
        candles: Sequence[Candle],
        available_jpy: Decimal,
        available_btc: Decimal,
        risk: RiskManager,
        market_data_real: bool,
        market_data_fresh: bool,
        connection: ConnectionSnapshot | None,
        private_api_ok: bool,
        kill_switch: bool,
        pending_order: bool,
        open_orders: int = 0,
    ) -> PipelineResult:
        slog(
            "SIGNAL_CREATED",
            "strategy signal",
            kind=signal.kind,
            side=signal.side,
            reason=signal.reason,
            tp_pct=str(signal.tp_pct) if signal.tp_pct is not None else None,
            price=str(price),
        )
        if signal.side not in {"buy", "sell"}:
            return PipelineResult(signal, None, None, None, None, True, signal.reason or "hold")
        rate = self.rate_engine.decide(signal, candles, price=price)
        if not rate.ok:
            slog("EXECUTION_BLOCKED", "rate engine refused", reason=rate.reason)
            return PipelineResult(signal, rate, None, None, None, True, rate.reason)
        if signal.side == "buy" and signal.tp_pct != rate.take_profit_pct:
            signal = Signal(
                kind=signal.kind,
                side=signal.side,
                tp_pct=rate.take_profit_pct,
                reason=signal.reason,
                golden_cross=signal.golden_cross,
                cross_price=signal.cross_price,
                peak_price=signal.peak_price,
                origin_price=signal.origin_price,
                crossover_price_bp=signal.crossover_price_bp,
            )
        sizer = PositionSizer(self.cfg, risk)
        if signal.side == "buy":
            plan = sizer.plan_buy(
                available_jpy=available_jpy,
                available_btc=available_btc,
                price=price,
                rate=rate,
            )
        else:
            plan = sizer.plan_sell(
                available_jpy=available_jpy,
                available_btc=available_btc,
                price=price,
            )
        slog(
            "POSITION_SIZE_CALCULATED",
            "size",
            side=plan.side,
            amount=str(plan.amount),
            planned_order_jpy=str(plan.planned_order_jpy),
            reason=plan.reason,
            ok=plan.ok,
        )
        if not plan.ok:
            slog("TRADE_BLOCKED", f"reason={plan.reason}", side=signal.side)
            return PipelineResult(signal, rate, plan, None, None, True, plan.reason)
        gate = self.gate.evaluate(
            signal=signal,
            amount=plan.amount,
            price=plan.price,
            market_data_real=market_data_real,
            market_data_fresh=market_data_fresh,
            connection=connection,
            private_api_ok=private_api_ok,
            balance_ok=available_jpy > ZERO or signal.side == "sell",
            kill_switch=kill_switch,
            pending_order=pending_order,
            rate=rate,
            open_orders=open_orders,
        )
        if gate.would_submit:
            slog(
                "WOULD_SUBMIT_ORDER",
                "LIVE_READY stand-in",
                pair=self.cfg.pair,
                side=plan.side,
                amount=str(plan.amount),
                price=str(plan.price),
                kind=signal.kind,
            )
            dummy = OrderResult(
                True,
                "would_submit",
                True,
                False,
                None,
                "UNFILLED",
                ZERO,
                ZERO,
                None,
                None,
            )
            return PipelineResult(signal, rate, plan, gate, dummy, True, "live_ready")
        if gate.blocked:
            if self.cfg.dry_run:
                order = self.orders.place(signal, plan)
                return PipelineResult(signal, rate, plan, gate, order, False, "")
            return PipelineResult(signal, rate, plan, gate, None, True, gate.reason)
        slog(
            "ORDER_REQUESTED",
            "submitting to OrderExecutor",
            side=plan.side,
            amount=str(plan.amount),
            price=str(plan.price),
        )
        order = self.orders.place(signal, plan)
        return PipelineResult(signal, rate, plan, gate, order, False, "")
