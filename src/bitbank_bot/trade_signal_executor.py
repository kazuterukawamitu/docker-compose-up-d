"""Single path from strategy signal to Bitbank order (or WOULD_SUBMIT_ORDER).

Strategies never call create_order. OrderExecutor is the only POST caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from bitbank_bot.amounts import AmountPlan
from bitbank_bot.config import MODE_LIVE_READY, Config
from bitbank_bot.execution_gate import ExecutionGate, GateContext
from bitbank_bot.logging_setup import slog
from bitbank_bot.market_data import Candle
from bitbank_bot.money import ZERO
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
    ) -> SubmitOutcome:
        mode = self.cfg.resolved_trading_mode()
        rate = self.rates.decide(signal, candles, stale=not market_data_fresh)
        if signal.tp_pct is not None and rate.take_profit_pct is not None:
            signal.tp_pct = rate.take_profit_pct
        ctx = GateContext(
            signal=signal,
            market_data_real=market_data_real,
            market_data_fresh=market_data_fresh,
            amount=plan.amount,
            amount_ok=plan.ok,
            kill_switch=kill_switch,
            pending_order=pending_order,
            open_order_conflict=False,
            ws_stale=ws_stale,
            explicit_synthetic=explicit_synthetic,
            ticker_mismatch=ticker_mismatch,
            rate_ok=rate.ok,
            extra_reason=extra_reason,
        )
        decision = self.gate.evaluate(ctx)
        if not decision.allowed:
            return SubmitOutcome(None, plan, decision.reason, mode)
        slog(
            "ORDER_PATH",
            "passing OrderExecutor",
            mode=mode,
            side=signal.side,
            live=self.cfg.may_place_live_orders,
            would_submit=mode == MODE_LIVE_READY,
        )
        result = self.orders.place(signal, plan)
        return SubmitOutcome(result, plan, "", mode)
