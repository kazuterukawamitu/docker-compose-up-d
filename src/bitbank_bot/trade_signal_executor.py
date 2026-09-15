"""Single order path: TradeGate → OrderExecutor → Bitbank.

Strategies must not import this to call Bitbank directly. Engine is the caller.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from bitbank_bot.amounts import AmountPlan
from bitbank_bot.config import Config
from bitbank_bot.execution_gate import GateResult, amount_valid, evaluate as gate_evaluate
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import ZERO
from bitbank_bot.orders import OrderClient, OrderExecutor, OrderResult
from bitbank_bot.strategy import Signal
from bitbank_bot.trade_trace import checkpoint


class TradeSignalExecutor:
    def __init__(self, cfg: Config, client: OrderClient | None) -> None:
        self.cfg = cfg
        self.client = client
        self.orders = OrderExecutor(cfg, client)

    def submit(
        self,
        signal: Signal,
        plan: AmountPlan,
        *,
        trace_id: str,
        market_data_real: bool,
        market_data_fresh: bool,
        private_api_ok: bool,
        kill_switch: bool,
        duplicate_order: bool,
        open_order_conflict: bool,
        stale_websocket: bool,
    ) -> OrderResult:
        checkpoint(
            trace_id,
            "SIGNAL_CREATED",
            signal.kind,
            side=signal.side,
            reason=signal.reason,
            pair=self.cfg.pair,
            price=str(plan.price),
            amount=str(plan.amount),
        )
        gate: GateResult = gate_evaluate(
            self.cfg,
            signal,
            market_data_real=market_data_real,
            market_data_fresh=market_data_fresh,
            private_api_ok=private_api_ok,
            balance_ok=plan.ok or plan.reason not in {"insufficient", "INSUFFICIENT_BALANCE"},
            amount_ok=amount_valid(plan.amount, self.cfg.min_amount_btc) if plan.ok else False,
            kill_switch=kill_switch,
            duplicate_order=duplicate_order,
            open_order_conflict=open_order_conflict,
            stale_websocket=stale_websocket,
        )
        if not gate.allowed:
            checkpoint(trace_id, "TRADE_GATE", "FAIL", reason=gate.reason)
            return OrderResult(
                False,
                gate.reason,
                self.cfg.dry_run,
                False,
                None,
                None,
                ZERO,
                ZERO,
                None,
                None,
            )
        checkpoint(trace_id, "TRADE_GATE", "PASS", reason=gate.reason)
        if gate.reason == "would_submit":
            slog(
                "WOULD_SUBMIT_ORDER",
                "pair=btc_jpy",
                trace_id=trace_id,
                side=plan.side,
                amount=str(plan.amount),
                price=str(plan.price),
                trading_mode=self.cfg.trading_mode,
            )
            checkpoint(trace_id, "ORDER_REQUEST", "WOULD_SUBMIT", side=plan.side)
            return OrderResult(
                True,
                "would_submit",
                True,
                False,
                None,
                "UNFILLED",
                ZERO,
                ZERO,
                None,
                {"would_submit": True},
            )
        checkpoint(
            trace_id,
            "ORDER_REQUEST",
            "submit",
            side=plan.side,
            amount=str(plan.amount),
            price=str(plan.price),
        )
        result = self.orders.place(signal, plan)
        if result.order_id:
            checkpoint(
                trace_id,
                "ORDER_ID_RECEIVED",
                result.status or "",
                order_id=result.order_id,
                executed_amount=str(result.executed_amount),
            )
        elif not result.ok:
            checkpoint(trace_id, "ORDER_REQUEST", "FAIL", reason=result.reason)
        return result

    def poll(self, order_id: str, fallback_amount: Decimal) -> OrderResult:
        return self.orders.poll(order_id, fallback_amount)

    def active_orders(self) -> list[dict[str, Any]]:
        return self.orders.active_orders()
