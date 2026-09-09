"""Unidirectional trade path used by Engine.

Strategy → SignalCandidate → RateEngine → TradeGate → OrderExecutor → FillTracker

This file does not talk to Bitbank URLs. All REST goes through OrderExecutor
and RestClient. DRY_RUN never calls create_order.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence
from uuid import uuid4

from bitbank_bot.amounts import AmountPlan, PositionSizer
from bitbank_bot.config import Config
from bitbank_bot.execution_gate import GateContext, GateResult, evaluate_gate, stale_price_deviation
from bitbank_bot.logging_setup import slog
from bitbank_bot.market_data import Candle
from bitbank_bot.money import D, ZERO
from bitbank_bot.orders import OrderExecutor, OrderResult
from bitbank_bot.rate_engine import RateDecision, RateEngine
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import MarketSnapshot, Signal


@dataclass(frozen=True)
class SignalCandidate:
    side: str
    trigger_price: Decimal
    current_price: Decimal
    strategy: str
    score: float
    reason: str
    kind: str
    tp_pct: Decimal | None
    previous_price: Decimal | None = None


@dataclass
class SignalStats:
    buy: int = 0
    sell: int = 0
    hold: int = 0

    def note(self, signal: Signal) -> None:
        if signal.side == "buy":
            self.buy += 1
        elif signal.side == "sell":
            self.sell += 1
        else:
            self.hold += 1


def detect_cross(previous: Decimal, current: Decimal, trigger: Decimal) -> str | None:
    if previous < trigger <= current:
        return "cross_up"
    if previous > trigger >= current:
        return "cross_down"
    return None


class SignalAggregator:
    def choose(self, candidates: Sequence[SignalCandidate], prefer_sell: bool = True) -> SignalCandidate | None:
        buys = [c for c in candidates if c.side == "BUY"]
        sells = [c for c in candidates if c.side == "SELL"]
        if buys and sells:
            slog("STRATEGY", "BUY and SELL conflict; prefer SELL" if prefer_sell else "conflict prefer BUY")
            pool = sells if prefer_sell else buys
        elif sells:
            pool = sells
        elif buys:
            pool = buys
        else:
            return None
        return max(pool, key=lambda c: c.score)


class TradeSignalExecutor:
    """Single place Engine uses after a BUY/SELL signal is produced."""

    def __init__(self, cfg: Config, order_client: object | None) -> None:
        self.cfg = cfg
        self.rate_engine = RateEngine(cfg)
        self.executor = OrderExecutor(cfg, order_client)  # type: ignore[arg-type]
        self.stats = SignalStats()
        self.last_order_side: str | None = None
        self.last_order_mono: float = 0.0

    def candidate_from_signal(self, signal: Signal, snap: MarketSnapshot) -> SignalCandidate | None:
        if signal.side not in {"buy", "sell"}:
            return None
        trigger = signal.cross_price or snap.close
        return SignalCandidate(
            side=signal.side.upper(),
            trigger_price=trigger,
            current_price=snap.close,
            strategy=signal.kind,
            score=1.0,
            reason=signal.reason,
            kind=signal.kind,
            tp_pct=signal.tp_pct,
            previous_price=snap.prev_close,
        )

    def decide_rate(self, signal: Signal, candles: Sequence[Candle]) -> RateDecision:
        return self.rate_engine.decide(signal, candles)

    def size(
        self,
        signal: Signal,
        price: Decimal,
        jpy: Decimal,
        btc: Decimal,
        risk: RiskManager,
        rate: RateDecision,
    ) -> AmountPlan:
        sizer = PositionSizer(self.cfg, risk)
        if signal.side == "buy":
            return sizer.plan_buy(
                available_jpy=jpy,
                available_btc=btc,
                price=price,
                risk_pct=rate.risk_pct if rate.mode == "DYNAMIC" else None,
                stop_loss_pct=rate.stop_loss_pct if rate.mode == "DYNAMIC" else None,
                size_scale=rate.size_scale,
            )
        return sizer.plan_sell(available_jpy=jpy, available_btc=btc, price=price)

    def gate(
        self,
        signal: Signal,
        rate: RateDecision,
        plan: AmountPlan,
        ctx: GateContext,
    ) -> GateResult:
        ctx.amount = plan.amount
        ctx.balance_ok = plan.ok or ctx.balance_ok
        if not plan.ok:
            slog("EXECUTION_BLOCKED", "TRADE_BLOCKED", reason=plan.reason)
            return GateResult(False, plan.reason, False, False, {"plan_ok": False})
        return evaluate_gate(self.cfg, signal, rate, ctx)

    def submit(self, signal: Signal, plan: AmountPlan, gate: GateResult) -> OrderResult:
        request_id = str(uuid4())
        slog(
            "ORDER_REQUESTED",
            "submit_order",
            request_id=request_id,
            kind=signal.kind,
            side=plan.side,
            amount=str(plan.amount),
            price=str(plan.price),
            gate=gate.reason,
            trading_mode=self.cfg.trading_mode,
        )
        if not gate.proceed:
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
        result = self.executor.place(signal, plan)
        if result.order_id:
            slog("ORDER_ID_RECEIVED", "order_id", order_id=result.order_id, status=result.status)
        return result


def apply_rate_to_signal(signal: Signal, rate: RateDecision) -> Signal:
    if signal.side != "buy" or not rate.ok:
        return signal
    return Signal(
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


def ticker_stale(close: Decimal, ticker: Decimal | None, cfg: Config) -> bool:
    return stale_price_deviation(close, ticker, cfg.stale_price_dev_pct)
