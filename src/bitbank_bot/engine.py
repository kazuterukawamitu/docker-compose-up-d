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
from bitbank_bot.decision import buy_block_reason, price_exit, shannon_entropy, unrealized_jpy
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
from bitbank_bot.orders import OrderExecutor, OrderResult, incremental_notional
from bitbank_bot.preflight import preflight
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
    fee_jpy: Decimal = ZERO
    fee_btc: Decimal = ZERO
    placed_at_ms: int = 0


@dataclass
class BotState:
    position: Position | None
    risk: RiskManager
    last_candle_ts: int
    started_at: float
    pending: PendingOrder | None = None
    paper_jpy: Decimal = ZERO
    paper_btc: Decimal = ZERO


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
                fee_jpy=D(pos.get("fee_jpy") or 0),
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
            filled_amt = D(pending_raw.get("filled_amount") or 0)
            filled_notional = D(pending_raw.get("filled_notional") or 0)
            if filled_amt > ZERO and filled_notional <= ZERO:
                avg_price = D(pending_raw.get("average_price") or 0)
                if avg_price > ZERO:
                    filled_notional = filled_amt * avg_price
            pending = PendingOrder(
                order_id=str(pending_raw["order_id"]),
                side=str(pending_raw.get("side") or ""),
                kind=str(pending_raw.get("kind") or ""),
                tp_pct=D(tp_raw) if tp_raw not in (None, "") else None,
                index=int(pending_raw.get("index") or 0),
                timestamp_ms=int(pending_raw.get("timestamp_ms") or 0),
                amount=D(pending_raw.get("amount") or 0),
                filled_amount=filled_amt,
                filled_notional=filled_notional,
                fee_jpy=D(pending_raw.get("fee_jpy") or 0),
                fee_btc=D(pending_raw.get("fee_btc") or 0),
                placed_at_ms=int(pending_raw.get("placed_at_ms") or 0),
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
        avg_price = ZERO
        if state.pending.filled_amount > ZERO and state.pending.filled_notional > ZERO:
            avg_price = state.pending.filled_notional / state.pending.filled_amount
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
            "average_price": str(avg_price),
            "fee_jpy": str(state.pending.fee_jpy),
            "fee_btc": str(state.pending.fee_btc),
            "placed_at_ms": state.pending.placed_at_ms,
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
            "fee_jpy": str(state.position.fee_jpy),
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
        self.last_unrealized: Decimal = ZERO

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
        self.last_entropy = shannon_entropy(closes)
        if execute and state.pending:
            self._poll_pending(state)
            self._maybe_replace_stale_sell(state, closes[-1])
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
            self._log_decision_context(signal, snap.close, state)
            slog("STRATEGY", "signal", kind=signal.kind, reason=signal.reason, side=signal.side)
            if execute and is_last and state.position is not None and self.cfg.enable_protective_exits:
                protected = self._protective_signal(state, snap.close)
                if protected is not None:
                    if state.pending is not None and not self._release_pending(state):
                        slog(
                            "ORDER_STATUS",
                            "protective exit waiting; pending order still open",
                            kind=protected.kind,
                        )
                        self.last_block_reason = "pending_order"
                    elif state.position is not None and state.pending is None:
                        slog(
                            "STRATEGY",
                            "protective exit",
                            kind=protected.kind,
                            reason=protected.reason,
                        )
                        self._execute(
                            protected,
                            self._mark_price(snap.close),
                            snap.index,
                            snap.timestamp_ms,
                            state,
                            order_type="market",
                        )
                        signal = protected
                        if not heartbeat:
                            state.last_candle_ts = snap.timestamp_ms
                            if persist:
                                save_state(self.cfg.state_path, state)
                        self.last_signal = signal
                        continue
            if not execute or heartbeat:
                if heartbeat:
                    slog("STRATEGY", "candle already processed", candle_ts=snap.timestamp_ms)
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
                if state.pending:
                    slog("ORDER_STATUS", "pending live order; skip new signal")
                    self.last_block_reason = "pending_order"
                    signal = Signal.hold("pending_order")
                    state.last_candle_ts = snap.timestamp_ms
                    if persist:
                        save_state(self.cfg.state_path, state)
                    continue
                if (
                    signal.side == "buy"
                    and self.cfg.enable_htf_filter
                    and not self._explicit_synthetic
                ):
                    verdict = evaluate_htf(self._rest(), self.cfg)
                    if not verdict.allow_buy:
                        self.last_block_reason = verdict.reason
                        slog("STRATEGY", "BUY blocked by HTF", reason=verdict.reason)
                        signal = Signal.hold(verdict.reason)
                        state.last_candle_ts = snap.timestamp_ms
                        if persist:
                            save_state(self.cfg.state_path, state)
                        continue
                if signal.side == "buy":
                    fee_reason = buy_block_reason(
                        signal.tp_pct, self.cfg.taker_fee_rate, self.last_entropy
                    )
                    if fee_reason:
                        self.last_block_reason = fee_reason
                        slog(
                            "STRATEGY",
                            "BUY blocked; take-profit does not clear fees",
                            reason=fee_reason,
                            tp_pct=str(signal.tp_pct),
                            entropy=str(self.last_entropy),
                            daily_pnl=str(state.risk.daily_pnl),
                        )
                        signal = Signal.hold(fee_reason)
                        state.last_candle_ts = snap.timestamp_ms
                        if persist:
                            save_state(self.cfg.state_path, state)
                        continue
                if self.ws is not None and self.cfg.enable_websocket and self.ws.is_stale():
                    slog("WEBSOCKET", "stale data; skipping orders")
                    self.last_block_reason = "stale_websocket"
                    signal = Signal.hold("stale_websocket")
                    break
                self._execute(signal, snap.close, snap.index, snap.timestamp_ms, state)
            state.last_candle_ts = snap.timestamp_ms
            if persist:
                save_state(self.cfg.state_path, state)
        self.last_signal = signal
        return signal

    def _execute(
        self,
        signal: Signal,
        price: Decimal,
        index: int,
        ts: int,
        state: BotState,
        order_type: str | None = None,
    ) -> None:
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
            plan = sizer.plan_sell(available_jpy=jpy, available_btc=btc, price=price)
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
            result = executor.place(signal, plan, order_type=order_type)
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
        if result.reason == "canceled":
            slog(
                "ORDER_STATUS",
                "canceled; pending cleared",
                order_id=pending.order_id,
                status=result.status,
            )
            state.pending = None
            return
        if result.executed_amount <= pending.filled_amount:
            if result.reason == "canceled_partial":
                slog(
                    "ORDER_STATUS",
                    "canceled remainder; pending cleared",
                    order_id=pending.order_id,
                )
                state.pending = None
                return
            if result.reason == "fill":
                slog(
                    "ORDER_STATUS",
                    "order complete; pending cleared",
                    order_id=pending.order_id,
                )
                state.pending = None
                return
            slog(
                "ORDER_STATUS",
                "pending still unfilled; skip new orders",
                order_id=pending.order_id,
            )
            return
        delta = result.executed_amount - pending.filled_amount
        _cumulative, delta_notional = incremental_notional(
            pending.filled_notional, result.executed_amount, result.average_price
        )
        incr_avg = (delta_notional / delta) if delta > ZERO else result.average_price
        delta_fee = result.fee_jpy - pending.fee_jpy
        if delta_fee < ZERO:
            delta_fee = ZERO
        delta_fee_btc = result.fee_btc - pending.fee_btc
        if delta_fee_btc < ZERO:
            delta_fee_btc = ZERO
        delta_result = OrderResult(
            True,
            result.reason,
            False,
            False,
            pending.order_id,
            result.status,
            delta,
            incr_avg,
            delta_notional,
            result.raw,
            delta_fee,
            delta_fee_btc,
            result.fee_estimated,
            result.cumulative_filled,
            result.cumulative_notional if result.cumulative_notional is not None else _cumulative,
            result.cumulative_fee_jpy,
            result.cumulative_fee_btc,
        )
        signal = Signal(pending.kind, pending.side, pending.tp_pct, "pending_fill")
        plan = AmountPlan(
            side=pending.side,
            amount=pending.amount,
            price=incr_avg,
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
        self._apply_fill(
            signal, plan, delta_result, pending.index, pending.timestamp_ms, state, jpy, btc
        )

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
                placed_at_ms=int(time.time() * 1000),
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
        stage = "SIMULATED_FILL" if result.simulated or self.cfg.dry_run else "FILL"
        slog(
            stage,
            "paper ledger" if stage == "SIMULATED_FILL" else "ledger",
            target_jpy=str(plan.target_jpy),
            planned_order_jpy=str(plan.planned_order_jpy),
            actual_execution_jpy=str(actual_jpy),
            actual_balance_jpy=str(jpy),
            actual_balance_btc=str(btc),
            bitbank_jpy_unchanged=bool(self.cfg.dry_run or result.simulated),
            fee_jpy=str(result.fee_jpy),
            fee_estimated=result.fee_estimated,
        )
        received = result.executed_amount - (result.fee_btc if result.fee_btc > ZERO else ZERO)
        if received < ZERO:
            received = ZERO
        if result.simulated or (self.cfg.dry_run and not self.cfg.has_keys):
            if state.paper_jpy <= ZERO and state.paper_btc <= ZERO:
                state.paper_jpy = jpy
                state.paper_btc = btc
            if signal.side == "buy":
                state.paper_btc += received
                state.paper_jpy = max(ZERO, state.paper_jpy - actual_jpy - result.fee_jpy)
            elif signal.side == "sell":
                state.paper_btc = max(ZERO, state.paper_btc - result.executed_amount)
                state.paper_jpy += max(ZERO, actual_jpy - result.fee_jpy)
        if signal.side == "buy":
            if received <= ZERO:
                slog("ERROR", "fill fee consumed the base amount; position unchanged")
                return
            tp = signal.tp_pct if signal.tp_pct is not None else self.cfg.buy1_tp
            if state.position:
                total_amt = state.position.amount + received
                total_jpy = state.position.actual_execution_jpy + actual_jpy
                total_fee = state.position.fee_jpy + result.fee_jpy
                avg = (total_jpy / total_amt) if total_amt > ZERO else result.average_price
                state.position = Position(
                    amount=total_amt,
                    average_price=avg,
                    tp_pct=state.position.tp_pct,
                    entry_candle_index=state.position.entry_candle_index,
                    entry_candle_ts=state.position.entry_candle_ts,
                    actual_execution_jpy=total_jpy,
                    kind=state.position.kind,
                    fee_jpy=total_fee,
                )
            else:
                avg = (actual_jpy / received) if received > ZERO else result.average_price
                state.position = Position(
                    amount=received,
                    average_price=avg,
                    tp_pct=tp,
                    entry_candle_index=index,
                    entry_candle_ts=ts,
                    actual_execution_jpy=actual_jpy,
                    kind=signal.kind,
                    fee_jpy=result.fee_jpy,
                )
        elif signal.side == "sell" and state.position:
            pos_amt = state.position.amount
            sold = result.executed_amount
            if pos_amt <= ZERO or sold >= pos_amt:
                cost = state.position.actual_execution_jpy
                buy_fee = state.position.fee_jpy
                state.position = None
            else:
                fraction = sold / pos_amt
                cost = state.position.actual_execution_jpy * fraction
                buy_fee = state.position.fee_jpy * fraction
                state.position.amount = pos_amt - sold
                state.position.actual_execution_jpy -= cost
                state.position.fee_jpy -= buy_fee
            state.risk.record_realized_pnl(actual_jpy - result.fee_jpy - cost - buy_fee)
        if result.reason == "partial_fill" and result.order_id:
            prev = state.pending
            placed_at = int(time.time() * 1000)
            if prev is not None and prev.order_id == result.order_id and prev.placed_at_ms:
                placed_at = prev.placed_at_ms
            filled = (
                result.cumulative_filled
                if result.cumulative_filled is not None
                else (prev.filled_amount if prev else ZERO) + result.executed_amount
            )
            notional = (
                result.cumulative_notional
                if result.cumulative_notional is not None
                else (prev.filled_notional if prev else ZERO) + actual_jpy
            )
            fee_jpy = (
                result.cumulative_fee_jpy
                if result.cumulative_fee_jpy is not None
                else (prev.fee_jpy if prev else ZERO) + result.fee_jpy
            )
            fee_btc = (
                result.cumulative_fee_btc
                if result.cumulative_fee_btc is not None
                else (prev.fee_btc if prev else ZERO) + result.fee_btc
            )
            state.pending = PendingOrder(
                order_id=result.order_id,
                side=signal.side or "",
                kind=signal.kind,
                tp_pct=signal.tp_pct,
                index=index,
                timestamp_ms=ts,
                amount=plan.amount,
                filled_amount=filled,
                filled_notional=notional,
                fee_jpy=fee_jpy,
                fee_btc=fee_btc,
                placed_at_ms=placed_at,
            )
        elif result.reason != "partial_fill":
            state.pending = None

    def _mark_price(self, fallback: Decimal) -> Decimal:
        if self.ws is not None and not self.ws.is_stale():
            try:
                live = self.ws.last_price()
            except Exception:
                live = None
            if live:
                try:
                    parsed = D(live)
                except Exception:
                    parsed = ZERO
                if parsed > ZERO:
                    return parsed
        if self.last_public_last not in (None, "", "-"):
            try:
                parsed = D(self.last_public_last)
            except Exception:
                parsed = ZERO
            if parsed > ZERO:
                return parsed
        return D(fallback)

    def _log_decision_context(self, signal: Signal, close: Decimal, state: BotState) -> None:
        unrealized = ZERO
        if state.position is not None:
            unrealized = unrealized_jpy(
                state.position, self._mark_price(close), self.cfg.taker_fee_rate
            )
            self.last_unrealized = unrealized
        slog(
            "STRATEGY",
            "decision_inputs",
            granville=signal.kind,
            daily_pnl=str(state.risk.daily_pnl),
            unrealized_jpy=str(unrealized),
            entropy=str(self.last_entropy),
            taker_fee_rate=str(self.cfg.taker_fee_rate),
        )

    def _protective_signal(self, state: BotState, fallback: Decimal) -> Signal | None:
        if state.position is None:
            return None
        mark = self._mark_price(fallback)
        self.last_unrealized = unrealized_jpy(
            state.position, mark, self.cfg.taker_fee_rate
        )
        return price_exit(
            state.position,
            mark,
            stop_loss_pct=self.cfg.stop_loss_pct,
            taker_fee_rate=self.cfg.taker_fee_rate,
            max_daily_loss_jpy=self.cfg.max_daily_loss_jpy,
            daily_pnl_floor=self.cfg.daily_pnl_floor,
            daily_pnl=state.risk.daily_pnl,
        )

    def _release_pending(self, state: BotState) -> bool:
        pending = state.pending
        if pending is None:
            return True
        executor = OrderExecutor(self.cfg, self._rest() if self.cfg.has_keys else None)
        if self.cfg.may_place_live_orders:
            canceled = executor.cancel(pending.order_id)
            if not canceled.ok:
                slog(
                    "ORDER_STATUS",
                    "cancel failed; not replacing the order",
                    order_id=pending.order_id,
                    reason=canceled.reason,
                )
                return False
        self._poll_pending(state)
        if state.pending is not None and not self.cfg.may_place_live_orders:
            state.pending = None
        return state.pending is None

    def _maybe_replace_stale_sell(self, state: BotState, fallback: Decimal) -> None:
        pending = state.pending
        if pending is None or pending.side != "sell":
            return
        if not self.cfg.may_place_live_orders or self.cfg.sell_unfilled_sec <= 0:
            return
        if pending.placed_at_ms <= 0:
            return
        age_ms = int(time.time() * 1000) - pending.placed_at_ms
        if age_ms < self.cfg.sell_unfilled_sec * 1000:
            return
        slog(
            "ORDER_STATUS",
            "stale sell limit; replacing with market",
            order_id=pending.order_id,
            age_ms=age_ms,
        )
        kind = pending.kind or "SELL"
        tp_pct = pending.tp_pct
        index = pending.index
        stamp = pending.timestamp_ms
        if not self._release_pending(state):
            return
        if state.position is None:
            return
        self._execute(
            Signal(kind, "sell", tp_pct, "stale_sell_to_market"),
            self._mark_price(fallback),
            index,
            stamp,
            state,
            order_type="market",
        )

    def reconcile(self, state: BotState) -> None:
        """Match local position and pending orders to the exchange.

        Runs only when live orders are allowed. A dry-run must not rewrite
        the state file from account balances.
        """
        if not self.cfg.may_place_live_orders:
            return
        rest = self._rest()
        try:
            jpy = rest.free_amount("jpy")
            btc = rest.free_amount("btc")
            active = list(rest.get_active_orders(self.cfg.pair) or [])
        except Exception as exc:
            slog("ERROR", "reconcile failed", error=type(exc).__name__)
            return
        slog("RECONCILE", "exchange snapshot", jpy=str(jpy), btc=str(btc), active=len(active))
        if state.pending is not None:
            self._poll_pending(state)
        if state.pending is None and active:
            row = active[0] if isinstance(active[0], dict) else {}
            order_id = str(row.get("order_id") or "")
            if order_id:
                executed = D(row.get("executed_amount") or 0)
                average = D(row.get("average_price") or 0)
                side = str(row.get("side") or "")
                if executed > ZERO and average > ZERO and side == "buy":
                    received = executed
                    notional = executed * average
                    if state.position:
                        total_amt = state.position.amount + received
                        total_jpy = state.position.actual_execution_jpy + notional
                        total_fee = state.position.fee_jpy
                        avg = (total_jpy / total_amt) if total_amt > ZERO else average
                        state.position = Position(
                            amount=total_amt,
                            average_price=avg,
                            tp_pct=state.position.tp_pct,
                            entry_candle_index=state.position.entry_candle_index,
                            entry_candle_ts=state.position.entry_candle_ts,
                            actual_execution_jpy=total_jpy,
                            kind=state.position.kind,
                            fee_jpy=total_fee,
                        )
                        slog("RECONCILE", "added adopted fill to position", executed=str(executed))
                    else:
                        state.position = Position(
                            amount=received,
                            average_price=average,
                            tp_pct=self.cfg.buy1_tp,
                            entry_candle_index=-1,
                            entry_candle_ts=0,
                            actual_execution_jpy=notional,
                            kind="RECONCILED",
                            fee_jpy=ZERO,
                        )
                        slog("RECONCILE", "created position from adopted fill", executed=str(executed))
                remainder = D(row.get("start_amount") or 0) - executed
                if remainder > self.cfg.amount_precision:
                    state.pending = PendingOrder(
                        order_id=order_id,
                        side=side,
                        kind="RECONCILED",
                        tp_pct=None,
                        index=0,
                        timestamp_ms=int(row.get("ordered_at") or 0),
                        amount=D(row.get("start_amount") or 0),
                        filled_amount=executed,
                        filled_notional=executed * average,
                        placed_at_ms=int(time.time() * 1000),
                    )
                    slog("RECONCILE", "adopted active order with remainder", order_id=order_id, side=side)
        if state.position is None and btc >= self.cfg.min_amount_btc and state.pending is None:
            average, cost, fee = self._basis_from_trades(rest, btc)
            if average <= ZERO:
                mark = self._mark_price(ZERO)
                if mark <= ZERO:
                    try:
                        mark = D((rest.get_ticker(self.cfg.pair) or {}).get("last") or 0)
                    except Exception:
                        mark = ZERO
                average = mark
                cost = btc * mark
            if average > ZERO:
                state.position = Position(
                    amount=btc,
                    average_price=average,
                    tp_pct=self.cfg.buy1_tp,
                    entry_candle_index=-1,
                    entry_candle_ts=0,
                    actual_execution_jpy=cost,
                    kind="RECONCILED",
                    fee_jpy=fee,
                )
                slog(
                    "RECONCILE",
                    "adopted exchange btc",
                    amount=str(btc),
                    average=str(average),
                )
        elif (
            state.position is not None
            and state.pending is None
            and btc < self.cfg.min_amount_btc
        ):
            slog(
                "RECONCILE",
                "cleared local position; exchange btc below min",
                local=str(state.position.amount),
                exchange=str(btc),
            )
            state.position = None
        elif state.position is not None and btc >= self.cfg.min_amount_btc:
            gap = abs(state.position.amount - btc)
            if gap > self.cfg.amount_precision and state.position.amount > ZERO:
                scale = btc / state.position.amount
                state.position.actual_execution_jpy *= scale
                state.position.fee_jpy *= scale
                state.position.amount = btc
                slog("RECONCILE", "resized position to exchange btc", amount=str(btc))
        save_state(self.cfg.state_path, state)

    def _basis_from_trades(
        self, rest: RestClient, amount: Decimal
    ) -> tuple[Decimal, Decimal, Decimal]:
        getter = getattr(rest, "get_trade_history", None)
        if not callable(getter):
            return ZERO, ZERO, ZERO
        try:
            trades = getter(self.cfg.pair)
        except Exception as exc:
            slog("ERROR", "reconcile trade_history failed", error=type(exc).__name__)
            return ZERO, ZERO, ZERO
        if not isinstance(trades, list):
            return ZERO, ZERO, ZERO
        buys = [row for row in trades if str(row.get("side") or "").lower() == "buy"]
        buys.sort(key=lambda row: int(row.get("executed_at") or 0), reverse=True)
        remain = amount
        cost = ZERO
        fee = ZERO
        for row in buys:
            lot = D(row.get("amount") or 0)
            price = D(row.get("price") or 0)
            if lot <= ZERO or price <= ZERO or remain <= ZERO:
                continue
            take = lot if lot < remain else remain
            cost += take * price
            quote_fee = D(row.get("fee_amount_quote") or 0) + D(row.get("fee_occurred_amount") or 0)
            if quote_fee > ZERO:
                fee += quote_fee * (take / lot)
            remain -= take
        if cost <= ZERO:
            return ZERO, ZERO, ZERO
        covered = amount - remain
        if covered <= ZERO:
            return ZERO, ZERO, ZERO
        return cost / covered, cost, fee

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
            self._refresh_public_last(rest)
            self.reconcile(state)
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
        if synthetic:
            state.last_candle_ts = 0
        elif self.cfg.may_place_live_orders:
            self._refresh_public_last(rest)
            self.reconcile(state)
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

    def _paint(self, state: BotState, signal: Signal, last: str = "-") -> None:
        if self.screen is None:
            return
        pos = state.position
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
            daily_pnl=str(state.risk.daily_pnl),
            unrealized_jpy=str(self.last_unrealized),
            entropy=str(self.last_entropy),
        )
        self.screen.render(view)


def install_signal_handlers(engine: Engine) -> None:
    signal.signal(signal.SIGTERM, engine.request_stop)
    signal.signal(signal.SIGINT, engine.request_stop)
