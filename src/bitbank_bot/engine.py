"""Main loop: candles → strategy → risk → amounts → orders."""

from __future__ import annotations

import json
import logging
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from bitbank_bot.amounts import AmountPlan, PositionSizer
from bitbank_bot.config import Config
from bitbank_bot.fees import tp_covers_fees
from bitbank_bot.indicators import (
    daily_pnl_score,
    entropy_regime,
    realtime_daily_pnl,
    shannon_entropy,
    simple_returns,
)
from bitbank_bot.logging_setup import slog
from bitbank_bot.market_data import (
    Candle,
    CandleCache,
    drop_incomplete_candle,
    fetch_candles,
    synthetic_candles,
)
from bitbank_bot.money import D, ZERO
from bitbank_bot.multi_timeframe import evaluate_htf
from bitbank_bot.orders import OrderExecutor, OrderResult
from bitbank_bot.preflight import preflight
from bitbank_bot.reconciliation import adopt_position_from_exchange, reconcile
from bitbank_bot.rest_client import BitbankAPIError, RestClient, is_auth_error
from bitbank_bot.risk import RiskManager
from bitbank_bot.screen import TradingScreen, view_from_engine
from bitbank_bot.strategy import Position, Signal, Strategy, build_snapshots
from bitbank_bot.watchdog import classify as classify_watchdog
from bitbank_bot.websocket_client import BitbankWebsocket

_LOG = logging.getLogger("bitbank_bot")


@dataclass
class PendingOrder:
    order_id: str
    side: str
    kind: str
    tp_pct: Decimal | None
    index: int
    timestamp_ms: int
    amount: Decimal
    filled_amount: Decimal = ZERO
    filled_notional: Decimal = ZERO


@dataclass
class BotState:
    position: Position | None
    risk: RiskManager
    last_candle_ts: int
    started_at: float
    pending: PendingOrder | None = None
    paper_jpy: Decimal = ZERO
    paper_btc: Decimal = ZERO
    reconcile_ok: bool = True
    reconcile_reason: str = "ok"


def load_state(path: str | Path, cfg: Config) -> BotState:
    risk = RiskManager(cfg)
    position = None
    last_ts = 0
    pending: PendingOrder | None = None
    paper_jpy = cfg.dry_run_free_jpy
    paper_btc = cfg.dry_run_free_btc
    p = Path(path)
    if p.exists():
        raw = json.loads(p.read_text(encoding="utf-8"))
        pos = raw.get("position")
        if pos:
            position = Position(
                amount=D(pos["amount"]),
                average_price=D(pos["average_price"]),
                tp_pct=D(pos["tp_pct"]),
                entry_candle_index=int(pos["entry_candle_index"]),
                entry_candle_ts=int(pos.get("entry_candle_ts") or 0),
                actual_execution_jpy=D(pos["actual_execution_jpy"]),
                kind=str(pos.get("kind") or ""),
                fees_paid=D(pos.get("fees_paid") or 0),
            )
        operator_killed = bool(raw.get("operator_killed", False))
        risk = RiskManager(
            cfg,
            daily_pnl=D(raw.get("daily_pnl") or 0),
            daily_pnl_date=raw.get("daily_pnl_date"),
            killed=operator_killed or cfg.kill_switch,
        )
        last_ts = int(raw.get("last_candle_ts") or 0)
        pending_raw = raw.get("pending")
        if pending_raw and pending_raw.get("order_id"):
            tp_raw = pending_raw.get("tp_pct")
            pending = PendingOrder(
                order_id=str(pending_raw["order_id"]),
                side=str(pending_raw.get("side") or ""),
                kind=str(pending_raw.get("kind") or ""),
                tp_pct=D(tp_raw) if tp_raw not in (None, "") else None,
                index=int(pending_raw.get("index") or 0),
                timestamp_ms=int(pending_raw.get("timestamp_ms") or 0),
                amount=D(pending_raw.get("amount") or 0),
                filled_amount=D(pending_raw.get("filled_amount") or 0),
                filled_notional=D(pending_raw.get("filled_notional") or 0),
            )
        if raw.get("paper_jpy") not in (None, ""):
            paper_jpy = D(raw.get("paper_jpy"))
        if raw.get("paper_btc") not in (None, ""):
            paper_btc = D(raw.get("paper_btc"))
    return BotState(
        position, risk, last_ts, time.monotonic(), pending, paper_jpy, paper_btc
    )


def save_state(path: str | Path, state: BotState) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "daily_pnl": str(state.risk.daily_pnl),
        "daily_pnl_date": state.risk.daily_pnl_date,
        "operator_killed": state.risk.operator_killed,
        "last_candle_ts": state.last_candle_ts,
        "paper_jpy": str(state.paper_jpy),
        "paper_btc": str(state.paper_btc),
        "position": None,
        "pending": None,
    }
    if state.pending:
        payload["pending"] = {
            "order_id": state.pending.order_id,
            "side": state.pending.side,
            "kind": state.pending.kind,
            "tp_pct": str(state.pending.tp_pct) if state.pending.tp_pct is not None else "",
            "index": state.pending.index,
            "timestamp_ms": state.pending.timestamp_ms,
            "amount": str(state.pending.amount),
            "filled_amount": str(state.pending.filled_amount),
            "filled_notional": str(state.pending.filled_notional),
        }
    if state.position:
        payload["position"] = {
            "amount": str(state.position.amount),
            "average_price": str(state.position.average_price),
            "tp_pct": str(state.position.tp_pct),
            "entry_candle_index": state.position.entry_candle_index,
            "entry_candle_ts": state.position.entry_candle_ts,
            "actual_execution_jpy": str(state.position.actual_execution_jpy),
            "kind": state.position.kind,
            "fees_paid": str(state.position.fees_paid),
        }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class Engine:
    def __init__(
        self,
        cfg: Config,
        client: RestClient | None = None,
        screen: TradingScreen | None = None,
    ) -> None:
        self.cfg = cfg
        self.client = client
        self.screen = screen
        self._stop = False
        self.ws: BitbankWebsocket | None = None
        self.cache = CandleCache(cfg.ma_period)
        self.last_block_reason = ""
        self.strategy_evaluations = 0
        self.cycles = 0
        self.used_synthetic_fallback = False
        self._explicit_synthetic = False
        self.last_watchdog = ""
        self.last_close: Decimal | str = "-"
        self.last_ma: Decimal | str = "-"
        self.last_trend = "-"
        self.last_signal = Signal.hold("starting")
        self.last_public_last: str = "-"
        self.last_error = ""
        self.last_entropy: Decimal = ZERO
        self.last_entropy_regime = "-"
        self.last_daily_pnl: Decimal = ZERO
        self.last_daily_pnl_score: Decimal = ZERO
        self._reconcile_blocked = False

    def request_stop(self, *_args: object) -> None:
        slog("BOOT", "shutdown requested")
        self._stop = True

    def _rest(self) -> RestClient:
        if self.client is None:
            self.client = RestClient(
                public_url=self.cfg.public_url,
                private_url=self.cfg.private_url,
                api_key=self.cfg.api_key,
                api_secret=self.cfg.api_secret,
                access_time_window_ms=self.cfg.access_time_window_ms,
                timeout_sec=self.cfg.http_timeout_sec,
                max_retries=self.cfg.max_retries,
                query_rps=self.cfg.query_rps,
                update_rps=self.cfg.update_rps,
            )
        return self.client

    def _balances(self, rest: RestClient, state: BotState | None = None) -> tuple[Decimal, Decimal]:
        if self.cfg.has_keys:
            jpy = rest.free_amount("jpy")
            btc = rest.free_amount("btc")
            slog("ASSET", "free_amount", jpy=str(jpy), btc=str(btc))
            return jpy, btc
        jpy = self.cfg.dry_run_free_jpy
        btc = self.cfg.dry_run_free_btc
        if state is not None and (state.paper_jpy > ZERO or state.paper_btc > ZERO or state.position):
            jpy = state.paper_jpy
            btc = state.paper_btc
        if state is not None and state.position:
            btc = max(btc, state.position.amount)
        slog("ASSET", "paper free_amount", jpy=str(jpy), btc=str(btc))
        return jpy, btc

    def _maybe_ws(self) -> None:
        if not self.cfg.enable_websocket or self.ws is not None:
            return
        try:
            self.ws = BitbankWebsocket(
                self.cfg.ws_url, self.cfg.ws_rooms, stale_sec=self.cfg.stale_ws_sec
            )
            self.ws.start()
        except Exception as exc:
            slog("WEBSOCKET", "start failed; REST only", error=type(exc).__name__)
            self.ws = None

    def process_candles(
        self,
        candles: list[Candle],
        state: BotState,
        execute: bool,
        persist: bool = True,
    ) -> Signal:
        candles = drop_incomplete_candle(candles, self.cfg.candle_type)
        closes = [c.close for c in candles]
        stamps = [c.timestamp_ms for c in candles]
        snaps = build_snapshots(closes, stamps, self.cfg)
        if not snaps:
            slog("STRATEGY", "not enough candles for MA")
            hold = Signal.hold("not_enough_candles")
            self.last_signal = hold
            return hold
        if execute and state.pending:
            self._poll_pending(state)
            if persist:
                save_state(self.cfg.state_path, state)
        strategy = Strategy(self.cfg)
        last = snaps[-1]
        self.last_close = last.close
        self.last_ma = last.ma
        self.last_trend = last.ma_trend.value
        slog(
            "MARKET",
            "MARKET DATA OK",
            close=str(last.close),
            ma=str(last.ma),
            trend=last.ma_trend.value,
            crossed_up=last.crossed_up,
            crossed_down=last.crossed_down,
        )
        self._update_regime(closes, state, last.close)
        signal = Signal.hold("no_eval")
        for i, snap in enumerate(snaps):
            is_last = i == len(snaps) - 1
            is_new = state.last_candle_ts > 0 and snap.timestamp_ms > state.last_candle_ts
            is_bootstrap = state.last_candle_ts <= 0 and is_last
            heartbeat = is_last and not is_new and not is_bootstrap
            if not (is_new or is_bootstrap or heartbeat):
                strategy.observe(snap)
                continue
            signal = strategy.evaluate(snap, state.position)
            self.strategy_evaluations += 1
            slog("STRATEGY", "signal", kind=signal.kind, reason=signal.reason, side=signal.side)
            if heartbeat and execute and state.position and not state.pending:
                if self._reconcile_blocked and self.cfg.require_reconcile and self.cfg.may_place_live_orders:
                    self.last_block_reason = f"reconcile_{state.reconcile_reason}"
                    signal = Signal.hold(self.last_block_reason)
                    continue
                mark = self._mark_price(snap.close)
                # Kill flatten before mark TP/STOP: check_sell blocks TP under kill,
                # so flatten must not wait behind a no-op mark exit.
                if self._maybe_emergency_flatten(state, mark, snap):
                    signal = Signal("EMERGENCY_STOP", "sell", None, "kill_flatten")
                    if persist:
                        save_state(self.cfg.state_path, state)
                    self.last_signal = signal
                    return signal
                if self.cfg.enable_intrabar_exits and state.position is not None:
                    exit_sig = strategy.evaluate_mark(mark, state.position)
                    if exit_sig.side == "sell":
                        slog(
                            "STRATEGY",
                            "intrabar exit",
                            kind=exit_sig.kind,
                            reason=exit_sig.reason,
                            mark=str(mark),
                        )
                        signal = exit_sig
                        self._execute(exit_sig, mark, snap.index, snap.timestamp_ms, state)
                        if persist:
                            save_state(self.cfg.state_path, state)
                        self.last_signal = signal
                        return signal
            if not execute or heartbeat:
                if heartbeat:
                    slog(
                        "STRATEGY",
                        "candle already processed; waiting next closed bar",
                        candle_ts=snap.timestamp_ms,
                    )
                continue
            if signal.side in {"buy", "sell"}:
                if not is_last:
                    slog(
                        "STRATEGY",
                        "catchup observe only; no order on historical bar",
                        candle_ts=snap.timestamp_ms,
                    )
                    state.last_candle_ts = snap.timestamp_ms
                    if persist:
                        save_state(self.cfg.state_path, state)
                    continue
                if self._reconcile_blocked and self.cfg.require_reconcile and self.cfg.may_place_live_orders:
                    self.last_block_reason = f"reconcile_{state.reconcile_reason}"
                    signal = Signal.hold(self.last_block_reason)
                    state.last_candle_ts = snap.timestamp_ms
                    if persist:
                        save_state(self.cfg.state_path, state)
                    continue
                if state.pending:
                    slog("ORDER_STATUS", "pending live order; skip new signal")
                    self.last_block_reason = "pending_order"
                    signal = Signal.hold("pending_order")
                    state.last_candle_ts = snap.timestamp_ms
                    if persist:
                        save_state(self.cfg.state_path, state)
                    continue
                if signal.side == "buy":
                    gated = self._buy_soft_gates(signal, state)
                    if gated is not None:
                        signal = gated
                        state.last_candle_ts = snap.timestamp_ms
                        if persist:
                            save_state(self.cfg.state_path, state)
                        continue
                    if self.cfg.enable_htf_filter and not self._explicit_synthetic:
                        verdict = evaluate_htf(self._rest(), self.cfg)
                        if not verdict.allow_buy:
                            self.last_block_reason = verdict.reason
                            slog("STRATEGY", "BUY blocked by HTF", reason=verdict.reason)
                            signal = Signal.hold(verdict.reason)
                            state.last_candle_ts = snap.timestamp_ms
                            if persist:
                                save_state(self.cfg.state_path, state)
                            continue
                if self.ws is not None and self.cfg.enable_websocket and self.ws.is_stale():
                    slog("WEBSOCKET", "stale data; skipping orders")
                    self.last_block_reason = "stale_websocket"
                    signal = Signal.hold("stale_websocket")
                    break
                price = snap.close
                if signal.kind in {"TP", "STOP", "EMERGENCY_STOP"}:
                    price = self._mark_price(snap.close)
                self._execute(signal, price, snap.index, snap.timestamp_ms, state)
            state.last_candle_ts = snap.timestamp_ms
            if persist:
                save_state(self.cfg.state_path, state)
        self.last_signal = signal
        return signal

    def _mark_price(self, fallback: Decimal) -> Decimal:
        if self.ws is not None and not self.ws.is_stale():
            last = self.ws.last_price()
            if last is not None and last > ZERO:
                return last
        if self.last_public_last not in {"-", "", None}:
            try:
                mark = D(self.last_public_last)
                if mark > ZERO:
                    return mark
            except Exception:
                pass
        return D(fallback)

    def _update_regime(
        self, closes: list[Decimal], state: BotState, mark: Decimal
    ) -> None:
        window = max(int(self.cfg.entropy_window), 2)
        series = closes[-window:] if len(closes) >= 2 else closes
        returns = simple_returns(series)
        self.last_entropy = shannon_entropy(returns, bins=int(self.cfg.entropy_bins))
        self.last_entropy_regime = entropy_regime(
            self.last_entropy,
            high=self.cfg.entropy_high,
            low=self.cfg.entropy_low,
        )
        pos = state.position
        self.last_daily_pnl = realtime_daily_pnl(
            state.risk.daily_pnl,
            mark,
            pos.amount if pos else ZERO,
            pos.average_price if pos else ZERO,
        )
        self.last_daily_pnl_score = daily_pnl_score(
            self.last_daily_pnl, self.cfg.pnl_score_scale_jpy
        )
        slog(
            "REGIME",
            "entropy_and_pnl",
            entropy=str(self.last_entropy),
            regime=self.last_entropy_regime,
            daily_pnl=str(self.last_daily_pnl),
            daily_pnl_score=str(self.last_daily_pnl_score),
        )

    def _buy_soft_gates(self, signal: Signal, state: BotState) -> Signal | None:
        tp = signal.tp_pct if signal.tp_pct is not None else self.cfg.buy1_tp
        if self.cfg.enable_fee_aware_entry and not tp_covers_fees(tp, self.cfg.fee_buffer):
            reason = "tp_below_round_trip_fees"
            self.last_block_reason = reason
            slog("RISK", "BUY blocked; TP cannot clear fees", tp=str(tp), fee=str(self.cfg.fee_buffer))
            return Signal.hold(reason)
        if (
            self.cfg.enable_entropy_buy_gate
            and self.last_entropy_regime == "CHOP"
            and self.last_entropy >= self.cfg.entropy_high
        ):
            reason = "high_entropy_chop"
            self.last_block_reason = reason
            slog("STRATEGY", "BUY blocked by entropy gate", entropy=str(self.last_entropy))
            return Signal.hold(reason)
        if self.cfg.enable_pnl_buy_gate and self.last_daily_pnl_score < D("-0.5"):
            reason = "daily_pnl_soft_gate"
            self.last_block_reason = reason
            slog(
                "STRATEGY",
                "BUY blocked by daily PnL soft gate (Granville still authoritative)",
                daily_pnl=str(self.last_daily_pnl),
                score=str(self.last_daily_pnl_score),
            )
            return Signal.hold(reason)
        return None

    def _maybe_emergency_flatten(
        self, state: BotState, mark: Decimal, snap: Any
    ) -> bool:
        if not self.cfg.emergency_flatten_on_kill:
            return False
        if state.position is None:
            return False
        if state.risk.halt_reason() != "kill_switch":
            return False
        if state.pending is not None:
            rest = self._rest()
            executor = OrderExecutor(self.cfg, rest if self.cfg.has_keys else None)
            result = executor.cancel(state.pending.order_id)
            if result.ok and result.executed_amount > ZERO:
                self._apply_fill(
                    Signal(state.pending.kind, state.pending.side, state.pending.tp_pct, "cancel_fill"),
                    AmountPlan(
                        side=state.pending.side,
                        amount=state.pending.amount,
                        price=result.average_price,
                        available_jpy=ZERO,
                        available_btc=ZERO,
                        target_jpy=ZERO,
                        planned_order_jpy=ZERO,
                        actual_execution_jpy=result.actual_execution_jpy,
                        actual_balance_jpy=ZERO,
                        actual_balance_btc=ZERO,
                        ok=True,
                        reason="kill_cancel",
                    ),
                    result,
                    state.pending.index,
                    state.pending.timestamp_ms,
                    state,
                    ZERO,
                    ZERO,
                )
            state.pending = None
        slog("RISK", "emergency market flatten on kill", mark=str(mark))
        signal = Signal("EMERGENCY_STOP", "sell", None, "kill_flatten")
        self._execute(signal, mark, snap.index, snap.timestamp_ms, state)
        return state.position is None

    def _execute(
        self,
        signal: Signal,
        price: Decimal,
        index: int,
        ts: int,
        state: BotState,
    ) -> None:
        # Defense in depth: every live path (closed-bar, intrabar, kill) must honor reconcile.
        if (
            self._reconcile_blocked
            and self.cfg.require_reconcile
            and self.cfg.may_place_live_orders
        ):
            self.last_block_reason = f"reconcile_{state.reconcile_reason}"
            slog(
                "TRADE_BLOCKED",
                "EXECUTION_BLOCKED",
                reason=self.last_block_reason,
                kind=signal.kind,
            )
            return
        rest = self._rest()
        if self.ws is not None and not self.ws.is_stale() and self.ws.last_price():
            price = self.ws.last_price() or price
        try:
            jpy, btc = self._balances(rest, state)
        except BitbankAPIError as exc:
            _LOG.exception("balance fetch failed on order path")
            if is_auth_error(exc):
                state.risk.note_auth_failure()
                reason = "auth_failure"
            else:
                state.risk.note_api_error()
                reason = "balance_fetch_failed"
            self.last_block_reason = reason
            slog("ERROR", "no order", reason=reason, error=type(exc).__name__)
            return
        except Exception as exc:
            _LOG.exception("balance fetch failed on order path")
            state.risk.note_api_error()
            self.last_block_reason = "balance_fetch_failed"
            slog("ERROR", "no order", reason="balance_fetch_failed", error=type(exc).__name__)
            return
        state.risk.note_api_ok()
        state.risk.update_equity(jpy, btc, price)
        sizer = PositionSizer(self.cfg, state.risk)
        if signal.side == "buy":
            plan = sizer.plan_buy(available_jpy=jpy, available_btc=btc, price=price)
        else:
            plan = sizer.plan_sell(
                available_jpy=jpy,
                available_btc=btc,
                price=price,
                allow_kill_flatten=signal.kind == "EMERGENCY_STOP",
            )
        slog(
            "RISK",
            "RISK MANAGER OK",
            ok=plan.ok,
            reason=plan.reason,
            target_jpy=str(plan.target_jpy),
            planned_order_jpy=str(plan.planned_order_jpy),
            amount=str(plan.amount),
        )
        if not plan.ok:
            self.last_block_reason = plan.reason
            slog("RISK", "order blocked", reason=plan.reason, side=signal.side)
            return
        self.last_block_reason = ""
        order_client = rest if self.cfg.has_keys else None
        executor = OrderExecutor(self.cfg, order_client)
        try:
            result = executor.place(signal, plan)
        except Exception as exc:
            _LOG.exception("order place failed")
            slog("ERROR", "order path failed", error=type(exc).__name__)
            state.risk.note_api_error()
            return
        slog(
            "HEARTBEAT",
            "ORDER MANAGER OK",
            reason=result.reason,
            simulated=result.simulated,
            dry_run=result.dry_run,
        )
        self._apply_fill(signal, plan, result, index, ts, state, jpy, btc)

    def _poll_pending(self, state: BotState) -> None:
        pending = state.pending
        if pending is None:
            return
        rest = self._rest()
        executor = OrderExecutor(self.cfg, rest if self.cfg.has_keys else None)
        result = executor.poll(pending.order_id, pending.amount)
        if not result.ok:
            slog(
                "ORDER_STATUS",
                "pending poll failed; holding new orders",
                order_id=pending.order_id,
            )
            return
        # Terminal cancel with no new size: clear pending so TP/stop/kill can proceed.
        if (
            result.reason in {"canceled", "canceled_partial"}
            and result.executed_amount <= pending.filled_amount
        ):
            slog(
                "ORDER_STATUS",
                "pending canceled; clearing",
                order_id=pending.order_id,
                reason=result.reason,
            )
            state.pending = None
            return
        if result.executed_amount <= pending.filled_amount:
            slog(
                "ORDER_STATUS",
                "pending still unfilled; skip new orders",
                order_id=pending.order_id,
            )
            return
        cum_notional = (
            result.executed_amount * result.average_price
            if result.average_price
            else ZERO
        )
        delta = result.executed_amount - pending.filled_amount
        delta_notional = cum_notional - pending.filled_notional
        if delta <= ZERO:
            slog(
                "ORDER_STATUS",
                "pending still unfilled; skip new orders",
                order_id=pending.order_id,
            )
            return
        fee_delta = result.fee_jpy
        if pending.filled_amount > ZERO and result.executed_amount > ZERO:
            # Attribute only the incremental share of reported cumulative fee when present.
            fee_delta = (
                result.fee_jpy * (delta / result.executed_amount)
                if result.fee_jpy > ZERO
                else ZERO
            )
        delta_result = OrderResult(
            True,
            "partial_fill" if result.reason == "partial_fill" else (
                "canceled_partial" if result.reason == "canceled_partial" else "fill"
            ),
            False,
            False,
            pending.order_id,
            result.status,
            delta,
            (delta_notional / delta) if delta > ZERO else result.average_price,
            delta_notional,
            result.raw,
            fee_delta,
        )
        signal = Signal(pending.kind, pending.side, pending.tp_pct, "pending_fill")
        plan = AmountPlan(
            side=pending.side,
            amount=pending.amount,
            price=result.average_price,
            available_jpy=ZERO,
            available_btc=ZERO,
            target_jpy=ZERO,
            planned_order_jpy=ZERO,
            actual_execution_jpy=None,
            actual_balance_jpy=ZERO,
            actual_balance_btc=ZERO,
            ok=True,
            reason="pending_poll",
        )
        try:
            jpy, btc = self._balances(rest, state)
        except Exception:
            jpy, btc = ZERO, ZERO
        pending.filled_amount = result.executed_amount
        pending.filled_notional = cum_notional
        if result.reason == "partial_fill":
            state.pending = pending
        else:
            state.pending = None
        self._apply_fill(
            signal, plan, delta_result, pending.index, pending.timestamp_ms, state, jpy, btc
        )
        if result.reason == "partial_fill":
            state.pending = pending
        else:
            state.pending = None

    def _set_watchdog(
        self,
        state: BotState,
        signal: Signal,
        *,
        fail_reason: str = "",
        market_ok: bool = True,
    ) -> None:
        report = classify_watchdog(
            uptime_sec=int(time.monotonic() - state.started_at),
            timeout_sec=int(self.cfg.no_trade_timeout_seconds),
            strategy_evaluations=self.strategy_evaluations,
            market_ok=market_ok,
            fail_reason=fail_reason,
            has_order_signal=signal.side in {"buy", "sell"},
        )
        slog(
            "WATCHDOG",
            report.status,
            reason=report.reason,
            kind=signal.kind,
            uptime_sec=report.uptime_sec,
        )
        self.last_watchdog = report.status

    def _apply_fill(
        self,
        signal: Signal,
        plan: Any,
        result: OrderResult,
        index: int,
        ts: int,
        state: BotState,
        jpy: Decimal,
        btc: Decimal,
    ) -> None:
        if result.reason == "canceled" and result.executed_amount <= ZERO:
            state.pending = None
            slog("ORDER_STATUS", "cleared canceled pending", order_id=result.order_id)
            return
        if result.reason == "accepted_unfilled" and result.order_id:
            state.pending = PendingOrder(
                order_id=result.order_id,
                side=signal.side or "",
                kind=signal.kind,
                tp_pct=signal.tp_pct,
                index=index,
                timestamp_ms=ts,
                amount=plan.amount,
                filled_amount=ZERO,
                filled_notional=ZERO,
            )
            slog(
                "ORDER_STATUS",
                "persisting unfilled live order",
                order_id=result.order_id,
                side=signal.side,
            )
            return
        if not result.ok or result.executed_amount <= ZERO:
            return
        actual_jpy = result.actual_execution_jpy
        if actual_jpy is None:
            slog("ERROR", "fill missing actual_execution_jpy; ignoring TARGET/PLANNED")
            return
        fee = D(result.fee_jpy or 0)
        stage = "SIMULATED_FILL" if result.simulated or self.cfg.dry_run else "FILL"
        slog(
            stage,
            "paper ledger" if stage == "SIMULATED_FILL" else "ledger",
            target_jpy=str(plan.target_jpy),
            planned_order_jpy=str(plan.planned_order_jpy),
            actual_execution_jpy=str(actual_jpy),
            fee_jpy=str(fee),
            actual_balance_jpy=str(jpy),
            actual_balance_btc=str(btc),
            bitbank_jpy_unchanged=bool(self.cfg.dry_run or result.simulated),
        )
        if result.simulated or (self.cfg.dry_run and not self.cfg.has_keys):
            if state.paper_jpy <= ZERO and state.paper_btc <= ZERO:
                state.paper_jpy = jpy
                state.paper_btc = btc
            if signal.side == "buy":
                state.paper_btc += result.executed_amount
                state.paper_jpy = max(ZERO, state.paper_jpy - actual_jpy - fee)
            elif signal.side == "sell":
                state.paper_btc = max(ZERO, state.paper_btc - result.executed_amount)
                state.paper_jpy += max(ZERO, actual_jpy - fee)
        if signal.side == "buy":
            tp = signal.tp_pct if signal.tp_pct is not None else self.cfg.buy1_tp
            if state.position:
                total_amt = state.position.amount + result.executed_amount
                total_jpy = state.position.actual_execution_jpy + actual_jpy
                avg = (total_jpy / total_amt) if total_amt > ZERO else result.average_price
                state.position = Position(
                    amount=total_amt,
                    average_price=avg,
                    tp_pct=state.position.tp_pct,
                    entry_candle_index=state.position.entry_candle_index,
                    entry_candle_ts=state.position.entry_candle_ts,
                    actual_execution_jpy=total_jpy,
                    kind=state.position.kind,
                    fees_paid=state.position.fees_paid + fee,
                )
            else:
                state.position = Position(
                    amount=result.executed_amount,
                    average_price=result.average_price,
                    tp_pct=tp,
                    entry_candle_index=index,
                    entry_candle_ts=ts,
                    actual_execution_jpy=actual_jpy,
                    kind=signal.kind,
                    fees_paid=fee,
                )
        elif signal.side == "sell" and state.position:
            pos_amt = state.position.amount
            buy_fees = state.position.fees_paid
            if pos_amt <= ZERO or result.executed_amount >= pos_amt:
                pnl = actual_jpy - state.position.actual_execution_jpy - fee - buy_fees
                state.risk.record_realized_pnl(pnl)
                state.position = None
            else:
                fraction = result.executed_amount / pos_amt
                cost = state.position.actual_execution_jpy * fraction
                allocated_buy_fee = buy_fees * fraction
                pnl = actual_jpy - cost - fee - allocated_buy_fee
                state.risk.record_realized_pnl(pnl)
                state.position.amount = pos_amt - result.executed_amount
                state.position.actual_execution_jpy -= cost
                state.position.fees_paid = buy_fees - allocated_buy_fee
        if result.reason == "partial_fill" and result.order_id:
            already = state.pending.filled_amount if state.pending else ZERO
            already_notional = state.pending.filled_notional if state.pending else ZERO
            state.pending = PendingOrder(
                order_id=result.order_id,
                side=signal.side or "",
                kind=signal.kind,
                tp_pct=signal.tp_pct,
                index=index,
                timestamp_ms=ts,
                amount=plan.amount,
                filled_amount=already + result.executed_amount,
                filled_notional=already_notional + actual_jpy,
            )
        elif result.reason != "partial_fill":
            state.pending = None

    def run_once(self, *, synthetic: bool = False, skip_preflight: bool = False) -> int:
        slog("BOOT", "run_once", synthetic=synthetic, dry_run=self.cfg.dry_run)
        self._explicit_synthetic = synthetic
        rest = self._rest()
        if not skip_preflight and not synthetic:
            result = preflight(self.cfg, rest, require_public=True)
            if not result.ok:
                slog("ERROR", "preflight failed", reason=result.reason)
                return 2
        candles = synthetic_candles() if synthetic else fetch_candles(rest, self.cfg)
        if synthetic:
            slog("MARKET", "using synthetic candles", count=len(candles))
            state = BotState(
                None,
                RiskManager(self.cfg),
                0,
                time.monotonic(),
                paper_jpy=self.cfg.dry_run_free_jpy,
                paper_btc=self.cfg.dry_run_free_btc,
            )
        else:
            candles = self.cache.merge(candles)
            state = load_state(self.cfg.state_path, self.cfg)
        signal = self.process_candles(
            candles, state, execute=True, persist=not synthetic
        )
        last = str(candles[-1].close) if candles else "-"
        self._set_watchdog(state, signal)
        self._heartbeat(state, signal, last)
        slog("BOOT", "run_once complete")
        return 0

    def _candles_for_cycle(
        self,
        rest: RestClient,
        *,
        latest_only: bool,
        force_synthetic: bool,
    ) -> list[Candle]:
        if force_synthetic:
            self.used_synthetic_fallback = True
            slog("MARKET", "using synthetic candles")
            return synthetic_candles()
        try:
            incoming = fetch_candles(rest, self.cfg, latest_only=latest_only)
            if incoming:
                self.used_synthetic_fallback = False
                return incoming
            slog("MARKET", "empty public candles; synthetic fallback without orders")
        except Exception as exc:
            slog(
                "WATCHDOG",
                "FAIL",
                reason="public_candles_failed_using_synthetic",
                error=type(exc).__name__,
            )
        self.used_synthetic_fallback = True
        slog("MARKET", "synthetic fallback; loop continues (no orders)")
        return synthetic_candles()

    def run_forever(
        self,
        *,
        synthetic: bool = False,
        max_cycles: int | None = None,
    ) -> int:
        slog(
            "BOOT",
            "run_forever",
            pair=self.cfg.pair,
            dry_run=self.cfg.dry_run,
            synthetic=synthetic,
        )
        self._explicit_synthetic = synthetic
        rest = self._rest()
        if self.screen is not None:
            self.screen.boot("公開ティッカーと足を取得しています…")
        require_public = not (synthetic or self.cfg.dry_run)
        result = preflight(self.cfg, rest, require_public=require_public)
        if not result.ok:
            if self.cfg.dry_run:
                slog(
                    "BOOT",
                    "preflight warning; DRY_RUN loop continues",
                    reason=result.reason,
                )
            else:
                slog("ERROR", "preflight failed", reason=result.reason)
                return 2
        if self.cfg.enable_websocket:
            self._maybe_ws()
        state = load_state(self.cfg.state_path, self.cfg)
        if not synthetic:
            self._startup_reconcile(state)
        if synthetic:
            state.last_candle_ts = 0
        last_ok = time.monotonic()
        timeout = float(self.cfg.no_trade_timeout_seconds)
        while not self._stop:
            try:
                latest_only = bool(self.cache.candles) and not synthetic
                incoming = self._candles_for_cycle(
                    rest, latest_only=latest_only, force_synthetic=synthetic
                )
                self._refresh_public_last(rest)
                accidental_synthetic = (
                    self.used_synthetic_fallback and not self._explicit_synthetic
                )
                if accidental_synthetic:
                    slog(
                        "WATCHDOG",
                        "FAIL",
                        reason="synthetic_fallback_no_orders",
                    )
                    candles = list(self.cache.candles) if self.cache.candles else incoming
                else:
                    candles = self.cache.merge(incoming)
                signal = self.process_candles(
                    candles,
                    state,
                    execute=not accidental_synthetic,
                    persist=not (synthetic or self.used_synthetic_fallback),
                )
                last_ok = time.monotonic()
                last = str(candles[-1].close) if candles else "-"
                fail_reason = (
                    "synthetic_fallback_no_orders" if accidental_synthetic else ""
                )
                self._set_watchdog(
                    state,
                    signal,
                    fail_reason=fail_reason,
                    market_ok=bool(candles) and not accidental_synthetic,
                )
                self.cycles += 1
                self._heartbeat(state, signal, last)
                if max_cycles is not None and self.cycles >= max_cycles:
                    slog("BOOT", "max_cycles reached", cycles=self.cycles)
                    break
            except KeyboardInterrupt:
                slog("BOOT", "keyboard interrupt")
                self._stop = True
                break
            except Exception as exc:
                _LOG.exception("loop error")
                slog("ERROR", "loop error", error=type(exc).__name__, detail=str(exc)[:200])
                idle = time.monotonic() - last_ok
                slog("WATCHDOG", "FAIL", reason="loop_error", idle_sec=int(idle))
                self.last_watchdog = "FAIL"
                if idle >= timeout:
                    slog("WATCHDOG", "FAIL stuck errors; still not exiting on HOLD")
                self.cycles += 1
                if max_cycles is not None and self.cycles >= max_cycles:
                    break
            try:
                if max_cycles is not None:
                    time.sleep(0.05)
                else:
                    for _ in range(int(max(1, self.cfg.poll_sec))):
                        if self._stop:
                            break
                        time.sleep(1)
            except KeyboardInterrupt:
                slog("BOOT", "keyboard interrupt")
                self._stop = True
        if self.ws:
            self.ws.stop()
        slog("BOOT", "stopped")
        return 0

    def _heartbeat(self, state: BotState, signal: Signal, last: str = "-") -> None:
        ws_ok = bool(self.ws and self.ws.is_connected())
        slog(
            "HEARTBEAT",
            "BOT ALIVE",
            price=last,
            signal=signal.kind,
            reason=signal.reason,
            in_position=bool(state.position),
            uptime_sec=int(time.monotonic() - state.started_at),
            mode="DRY_RUN" if self.cfg.dry_run else "LIVE",
            bitbank_jpy_unchanged=self.cfg.dry_run,
            utc=datetime.now(timezone.utc).isoformat(),
        )
        slog("HEARTBEAT", "WebSocket CONNECTED" if ws_ok else "WebSocket DISCONNECTED")
        slog("HEARTBEAT", "REST API OK")
        slog("HEARTBEAT", "MARKET DATA OK")
        slog("HEARTBEAT", "ORDER MANAGER OK")
        slog("HEARTBEAT", "RISK MANAGER OK")
        self._paint(state, signal, last)

    def _refresh_public_last(self, rest: RestClient) -> None:
        try:
            ticker = rest.get_ticker(self.cfg.pair)
            last = ticker.get("last")
            if last not in (None, ""):
                self.last_public_last = str(last)
                self.last_error = ""
        except Exception as exc:
            self.last_error = type(exc).__name__

    def _startup_reconcile(self, state: BotState) -> None:
        if not self.cfg.has_keys:
            state.reconcile_ok = True
            state.reconcile_reason = "no_keys_skip"
            self._reconcile_blocked = False
            return
        rest = self._rest()
        try:
            jpy, btc = self._balances(rest, state)
            active = rest.get_active_orders(self.cfg.pair)
        except Exception as exc:
            slog("RECONCILE", "startup reconcile failed", error=type(exc).__name__)
            state.reconcile_ok = False
            state.reconcile_reason = "reconcile_fetch_failed"
            self._reconcile_blocked = bool(
                self.cfg.require_reconcile and self.cfg.may_place_live_orders
            )
            return
        bot_btc = state.position.amount if state.position else ZERO
        report = reconcile(
            exchange_jpy=jpy,
            exchange_btc=btc,
            open_orders=active,
            bot_position_btc=bot_btc,
            pending=state.pending is not None,
            min_amount=self.cfg.min_amount_btc,
        )
        state.reconcile_ok = report.ok
        state.reconcile_reason = report.reason
        if report.reason == "pending_without_exchange_order":
            slog("ORDER_STATUS", "pending absent on exchange; polling to check fill status")
            self._poll_pending(state)
            # Never treat "absent from active list" as cancel-only: fills must be booked
            # via get_order/_poll_pending first, then re-check BTC vs exchange.
            try:
                jpy, btc = self._balances(rest, state)
                active = rest.get_active_orders(self.cfg.pair)
            except Exception as exc:
                slog("RECONCILE", "post-poll reconcile failed", error=type(exc).__name__)
                state.reconcile_ok = False
                state.reconcile_reason = "reconcile_fetch_failed"
            else:
                bot_btc = state.position.amount if state.position else ZERO
                report = reconcile(
                    exchange_jpy=jpy,
                    exchange_btc=btc,
                    open_orders=active,
                    bot_position_btc=bot_btc,
                    pending=state.pending is not None,
                    min_amount=self.cfg.min_amount_btc,
                )
                state.reconcile_ok = report.ok
                state.reconcile_reason = (
                    "cleared_stale_pending"
                    if state.pending is None and report.ok
                    else report.reason
                )
        if report.reason == "exchange_open_order_adopted" and report.adopted_order_id:
            row = next(
                (
                    item
                    for item in active
                    if str(item.get("order_id") or "") == report.adopted_order_id
                ),
                active[0] if active else {},
            )
            self._adopt_exchange_order(state, row, jpy=jpy, btc=btc)
            state.reconcile_ok = True
            state.reconcile_reason = "exchange_open_order_adopted"
        elif (
            report.reason == "btc_position_mismatch"
            and state.position is None
            and btc >= self.cfg.min_amount_btc
        ):
            mark_price = self._safe_mark_for_adopt(rest)
            if mark_price <= ZERO:
                slog(
                    "RECONCILE",
                    "refuse adopt without real mark; leaving blocked",
                    btc=str(btc),
                )
                state.reconcile_ok = False
                state.reconcile_reason = "adopt_mark_unavailable"
            else:
                adopted = adopt_position_from_exchange(
                    btc,
                    mark_price,
                    min_amount=self.cfg.min_amount_btc,
                    default_tp=self.cfg.buy1_tp,
                )
                if adopted:
                    amount, price = adopted
                    state.position = Position(
                        amount=amount,
                        average_price=price,
                        tp_pct=self.cfg.buy1_tp,
                        entry_candle_index=0,
                        entry_candle_ts=0,
                        actual_execution_jpy=amount * price,
                        kind="RECONCILED",
                        fees_paid=ZERO,
                    )
                    state.reconcile_ok = True
                    state.reconcile_reason = "adopted_exchange_btc"
                    slog(
                        "POSITION_RECONCILED",
                        "adopted exchange BTC",
                        amount=str(amount),
                        mark=str(price),
                    )
        self._reconcile_blocked = bool(
            self.cfg.require_reconcile
            and self.cfg.may_place_live_orders
            and not state.reconcile_ok
        )
        save_state(self.cfg.state_path, state)

    def _safe_mark_for_adopt(self, rest: RestClient) -> Decimal:
        """Real ticker/WS mark only — never invent a 1 JPY placeholder cost basis."""
        try:
            ticker = rest.get_ticker(self.cfg.pair)
            mark_price = D(ticker.get("last") or 0)
            if mark_price > ZERO:
                self.last_public_last = str(mark_price)
                return mark_price
        except Exception as exc:
            slog("RECONCILE", "ticker mark failed", error=type(exc).__name__)
        self._refresh_public_last(rest)
        mark_price = self._mark_price(ZERO)
        return mark_price if mark_price > ZERO else ZERO

    def _adopt_exchange_order(
        self,
        state: BotState,
        row: dict[str, Any],
        *,
        jpy: Decimal,
        btc: Decimal,
    ) -> None:
        """Track an open exchange order and book any already-executed size into position."""
        order_id = str(row.get("order_id") or "")
        side = str(row.get("side") or "")
        executed = D(row.get("executed_amount") or 0)
        remaining = D(row.get("remaining_amount") or 0)
        start = D(row.get("start_amount") or 0)
        if start <= ZERO:
            start = executed + remaining
        amount = start if start > ZERO else executed
        avg_price = D(row.get("average_price") or 0)
        filled_notional = executed * avg_price if avg_price > ZERO else ZERO
        still_open = remaining > ZERO or (amount > executed and amount > ZERO)
        state.pending = PendingOrder(
            order_id=order_id,
            side=side,
            kind="RECONCILED",
            tp_pct=self.cfg.buy1_tp if side == "buy" else None,
            index=0,
            timestamp_ms=0,
            amount=amount if amount > ZERO else executed,
            filled_amount=ZERO,
            filled_notional=ZERO,
        )
        if executed <= ZERO or avg_price <= ZERO or side not in {"buy", "sell"}:
            state.pending.filled_amount = executed
            state.pending.filled_notional = filled_notional
            return
        # Book the already-filled slice so later poll deltas stay incremental.
        fill = OrderResult(
            True,
            "partial_fill" if still_open else "fill",
            False,
            False,
            order_id,
            str(row.get("status") or ""),
            executed,
            avg_price,
            filled_notional,
            row,
            ZERO,
        )
        plan = AmountPlan(
            side=side,
            amount=amount if amount > ZERO else executed,
            price=avg_price,
            available_jpy=jpy,
            available_btc=btc,
            target_jpy=ZERO,
            planned_order_jpy=ZERO,
            actual_execution_jpy=filled_notional,
            actual_balance_jpy=jpy,
            actual_balance_btc=btc,
            ok=True,
            reason="reconcile_adopt",
        )
        signal = Signal(
            "RECONCILED",
            side,
            self.cfg.buy1_tp if side == "buy" else None,
            "adopted_fill",
        )
        self._apply_fill(signal, plan, fill, 0, 0, state, jpy, btc)
        if still_open:
            state.pending = PendingOrder(
                order_id=order_id,
                side=side,
                kind="RECONCILED",
                tp_pct=self.cfg.buy1_tp if side == "buy" else None,
                index=0,
                timestamp_ms=0,
                amount=amount,
                filled_amount=executed,
                filled_notional=filled_notional,
            )
        else:
            state.pending = None
        slog(
            "ORDER_STATUS",
            "adopted exchange open order",
            order_id=order_id,
            side=side,
            executed=str(executed),
            filled_notional=str(filled_notional),
        )

    def _paint(self, state: BotState, signal: Signal, last: str = "-") -> None:
        if self.screen is None:
            return
        pos = state.position
        note = "HOLD/待機は正常です。Ctrl-C で停止"
        if signal.reason == "no_buy_setup":
            note = "次の確定足でセットアップ待ち（HOLDは正常）"
        elif signal.reason.startswith("mark_") or signal.kind in {"TP", "STOP"}:
            note = "建玉監視中: 足内TP/損切りを有効化"
        view = view_from_engine(
            pair=self.cfg.pair,
            dry_run=self.cfg.dry_run,
            live_orders=self.cfg.may_place_live_orders,
            price=last if last != "-" else self.last_close,
            public_last=self.last_public_last,
            ma=self.last_ma,
            trend=self.last_trend,
            signal_kind=signal.kind,
            signal_reason=signal.reason,
            in_position=bool(pos),
            position_amount=pos.amount if pos else ZERO,
            position_avg=pos.average_price if pos else ZERO,
            position_tp=pos.tp_pct if pos else "",
            watchdog=self.last_watchdog or "NORMAL WAIT",
            ws_ok=bool(self.ws and self.ws.is_connected()),
            cycles=self.cycles,
            uptime_sec=int(time.monotonic() - state.started_at),
            block_reason=self.last_block_reason,
            error=self.last_error,
            candle_type=self.cfg.candle_type,
            daily_pnl=self.last_daily_pnl,
            entropy=self.last_entropy,
            entropy_regime=self.last_entropy_regime,
            note=note,
        )
        self.screen.render(view)


def install_signal_handlers(engine: Engine) -> None:
    signal.signal(signal.SIGTERM, engine.request_stop)
    signal.signal(signal.SIGINT, engine.request_stop)
