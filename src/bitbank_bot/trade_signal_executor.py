"""Single path from strategy signal to Bitbank order (or WOULD_SUBMIT_ORDER).

Strategies never call create_order. OrderExecutor is the only POST caller.
When README BUY/SELL conditions match and the gate is open, this path
always reaches OrderExecutor (paper fill in DRY_RUN, WOULD_SUBMIT in
LIVE_READY, POST only in dual-confirmed LIVE).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from bitbank_bot.amounts import AmountPlan, apply_size_mult
from bitbank_bot.config import MODE_LIVE_READY, Config
from bitbank_bot.execution_gate import ExecutionGate, GateContext
from bitbank_bot.logging_setup import slog
from bitbank_bot.market_data import Candle
from bitbank_bot.orders import OrderExecutor, OrderResult
from bitbank_bot.rate_engine import RateEngine
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import Signal


@dataclass
class SubmitOutcome:
    result: OrderResult | None
    plan: AmountPlan | None
    blocked: str
    mode: str


class TradeSignalExecutor:
    def __init__(
        self,
        cfg: Config,
        risk: RiskManager,
        order_client: Any | None,
    ) -> None:
        self.cfg = cfg
        self.risk = risk
        self.gate = ExecutionGate(cfg)
        self.rates = RateEngine(cfg)
        self.orders = OrderExecutor(cfg, order_client)

    def _open_order_conflict(self, requested: bool | None) -> bool:
        if requested is not None:
            return bool(requested)
        if self.orders.client is None:
            return False
        try:
            opens = self.orders.active_orders()
        except Exception as exc:
            slog(
                "EXECUTION_BLOCKED",
                "active_orders unreadable",
                error=type(exc).__name__,
                live=self.cfg.may_place_live_orders,
            )
            return bool(self.cfg.may_place_live_orders)
        return len(opens) > 0

    def submit(
        self,
        signal: Signal,
        plan: AmountPlan,
        candles: list[Candle],
        *,
        market_data_real: bool,
        market_data_fresh: bool,
        kill_switch: bool,
        pending_order: bool,
        ws_stale: bool,
        ticker_mismatch: bool = False,
        extra_reason: str = "",
        explicit_synthetic: bool = False,
        open_order_conflict: bool | None = None,
    ) -> SubmitOutcome:
        mode = self.cfg.resolved_trading_mode()
        rate = self.rates.decide(signal, candles, stale=not market_data_fresh)
        slog(
            "RATE_DECIDED",
            rate.reason,
            mode=rate.mode,
            regime=rate.market_regime,
            tp=str(rate.take_profit_pct) if rate.take_profit_pct is not None else None,
            sl=str(rate.stop_loss_pct) if rate.stop_loss_pct is not None else None,
            size_mult=str(rate.size_mult),
            ok=rate.ok,
        )
        if signal.tp_pct is not None and rate.take_profit_pct is not None:
            signal.tp_pct = rate.take_profit_pct
        sized = apply_size_mult(plan, self.cfg, rate.size_mult)
        conflict = self._open_order_conflict(open_order_conflict)
        ctx = GateContext(
            signal=signal,
            market_data_real=market_data_real,
            market_data_fresh=market_data_fresh,
            amount=sized.amount,
            amount_ok=sized.ok,
            kill_switch=kill_switch,
            pending_order=pending_order,
            open_order_conflict=conflict,
            ws_stale=ws_stale,
            explicit_synthetic=explicit_synthetic,
            ticker_mismatch=ticker_mismatch,
            rate_ok=rate.ok,
            extra_reason=extra_reason,
        )
        decision = self.gate.evaluate(ctx)
        if not decision.allowed:
            return SubmitOutcome(None, sized, decision.reason, mode)
        trace_id = uuid.uuid4().hex[:12]
        slog(
            "ORDER_PATH",
            "passing OrderExecutor",
            mode=mode,
            side=signal.side,
            live=self.cfg.may_place_live_orders,
            would_submit=mode == MODE_LIVE_READY,
            size_mult=str(rate.size_mult),
            trace_id=trace_id,
        )
        result = self.orders.place(signal, sized, trace_id=trace_id)
        return SubmitOutcome(result, sized, "", mode)
