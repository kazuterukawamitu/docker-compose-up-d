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

from bitbank_bot.adaptive import (
    gravity_well_escape_optimizer,
    multi_scenario_inference,
    probability_state_updater,
    self_healing_execution_guard,
    shannon_entropy,
    spline_end_slope,
)
from bitbank_bot.amounts import AmountPlan, PositionSizer
from bitbank_bot.config import Config
from bitbank_bot.fees import fill_fee_jpy, incremental_notional
from bitbank_bot.logging_setup import slog
from bitbank_bot.market_data import (
    Candle,
    CandleCache,
    drop_incomplete_candle,
    fetch_candles,
    synthetic_candles,
)
from bitbank_bot.money import D, ONE, ZERO
from bitbank_bot.reconcile import decide_reconcile
from bitbank_bot.multi_timeframe import evaluate_htf
from bitbank_bot.orders import OrderExecutor, OrderResult
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
    placed_at: float = 0.0
    average_price: Decimal = ZERO


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
                fees_jpy=D(pos.get("fees_jpy") or 0),
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
                placed_at=float(pending_raw.get("placed_at") or 0) or time.time(),
                average_price=D(pending_raw.get("average_price") or 0),
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
            "placed_at": state.pending.placed_at,
            "average_price": str(state.pending.average_price),
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
            "fees_jpy": str(state.position.fees_jpy),
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
        self.last_quote_ms = 0
        self.last_error = ""
        self._candle_fp: tuple[int, int, str] | None = None
        self._last_bar_index = 0
        self._closes: list[Decimal] = []
        self._returns: list[Decimal] = []
        self.entropy = ZERO
        self.posterior_up = D("0.333")
        self.posterior_down = D("0.333")
        self.hold_escape = "-"
        self.spline_slope = ZERO
        self.scenarios: dict[str, Decimal] = {}

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
            if isinstance(rest, RestClient) and hasattr(rest, "free_amounts"):
                amounts = rest.free_amounts()
                jpy = amounts.get("jpy", ZERO)
                btc = amounts.get("btc", ZERO)
            else:
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
        if execute and state.pending:
            self._poll_pending(state)
            if persist:
                save_state(self.cfg.state_path, state)
        if candles:
            self._observe_close(candles[-1].close)
            self._note_scenarios(candles[-1].close)
        if execute and candles:
            protective = self._protective_exit(
                state, self._last_bar_index, candles[-1].timestamp_ms
            )
            if protective is not None:
                self.last_signal = protective
                state.last_candle_ts = max(state.last_candle_ts, candles[-1].timestamp_ms)
                self._candle_fp = (
                    len(candles),
                    candles[-1].timestamp_ms,
                    str(candles[-1].close),
                )
                if persist:
                    save_state(self.cfg.state_path, state)
                return protective
        if candles:
            last_bar = candles[-1]
            fingerprint = (len(candles), last_bar.timestamp_ms, str(last_bar.close))
            if (
                self._candle_fp == fingerprint
                and state.last_candle_ts >= last_bar.timestamp_ms
                and state.position is None
            ):
                self.strategy_evaluations += 1
                slog(
                    "STRATEGY",
                    "cached signal",
                    kind=self.last_signal.kind,
                    reason=self.last_signal.reason,
                )
                if execute and state.pending is None:
                    self._retry_open_sell(
                        state,
                        self.last_signal,
                        last_bar.close,
                        self._last_bar_index,
                        last_bar.timestamp_ms,
                    )
                    if persist:
                        save_state(self.cfg.state_path, state)
                return self.last_signal
        closes = [c.close for c in candles]
        stamps = [c.timestamp_ms for c in candles]
        snaps = build_snapshots(closes, stamps, self.cfg)
        if not snaps:
            slog("STRATEGY", "not enough candles for MA")
            hold = Signal.hold("not_enough_candles")
            self.last_signal = hold
            return hold
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
            if is_last:
                self._last_bar_index = snap.index
            slog("STRATEGY", "signal", kind=signal.kind, reason=signal.reason, side=signal.side)
            if not execute:
                continue
            if heartbeat:
                slog("STRATEGY", "candle already processed", candle_ts=snap.timestamp_ms)
                if state.pending is None:
                    self._retry_open_sell(
                        state, signal, snap.close, snap.index, snap.timestamp_ms
                    )
                    if persist:
                        save_state(self.cfg.state_path, state)
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
                if self.ws is not None and self.cfg.enable_websocket and self.ws.is_stale():
                    slog("WEBSOCKET", "stale data; skipping orders")
                    self.last_block_reason = "stale_websocket"
                    signal = Signal.hold("stale_websocket")
                    break
                self._execute(signal, snap.close, snap.index, snap.timestamp_ms, state)
            state.last_candle_ts = snap.timestamp_ms
            if persist:
                save_state(self.cfg.state_path, state)
        if candles:
            self._candle_fp = (len(candles), candles[-1].timestamp_ms, str(candles[-1].close))
        self.last_signal = signal
        return signal

    def _retry_open_sell(
        self,
        state: BotState,
        signal: Signal,
        price: Decimal,
        index: int,
        ts: int,
    ) -> None:
        """Replace a timed-out exit on the same closed candle. Buys stay once per bar."""
        if state.pending is not None or state.position is None or signal.side != "sell":
            return
        self._execute(signal, price, index, ts, state)

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
        if self._quote_is_stale():
            self.last_block_reason = "stale_quote"
            slog("MARKET", "stale quote; skip order", quote_ms=self.last_quote_ms)
            return
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
            sell_btc = btc
            if state.position is not None and state.position.amount > ZERO:
                tracked = state.position.amount
                sell_btc = min(btc, tracked) if self.cfg.has_keys else tracked
            plan = sizer.plan_sell(available_jpy=jpy, available_btc=sell_btc, price=price)
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
        if signal.side == "buy" and not self._buy_guard_allows(signal, state):
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
            self._cancel_if_timed_out(state)
            return
        self._book_pending_delta(state, pending, result)
        if state.pending is not None and result.reason == "canceled":
            state.pending = None
            slog("ORDER_STATUS", "cleared canceled order", order_id=pending.order_id)
        if state.pending is not None:
            if result.executed_amount <= pending.filled_amount and result.reason != "canceled":
                slog(
                    "ORDER_STATUS",
                    "pending still unfilled; skip new orders",
                    order_id=pending.order_id,
                )
            self._cancel_if_timed_out(state)

    def _book_pending_delta(
        self, state: BotState, pending: PendingOrder, result: OrderResult
    ) -> None:
        if result.executed_amount <= pending.filled_amount:
            return
        delta_qty, delta_notional, incremental_avg = incremental_notional(
            pending.filled_amount,
            pending.average_price,
            result.executed_amount,
            result.average_price,
        )
        if delta_qty <= ZERO:
            return
        delta_result = OrderResult(
            True,
            result.reason,
            False,
            False,
            pending.order_id,
            result.status,
            delta_qty,
            incremental_avg,
            delta_notional,
            result.raw,
        )
        signal = Signal(pending.kind, pending.side, pending.tp_pct, "pending_fill")
        plan = AmountPlan(
            side=pending.side,
            amount=pending.amount,
            price=incremental_avg if incremental_avg > ZERO else ZERO,
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
            jpy, btc = self._balances(self._rest(), state)
        except Exception:
            jpy, btc = ZERO, ZERO
        self._apply_fill(
            signal, plan, delta_result, pending.index, pending.timestamp_ms, state, jpy, btc
        )
        if state.pending is not None and state.pending.order_id == pending.order_id:
            state.pending.average_price = result.average_price
            state.pending.filled_amount = result.executed_amount

    def _pending_limit(self, pending: PendingOrder) -> int:
        if pending.side == "sell":
            return int(self.cfg.sell_order_timeout_seconds)
        return int(self.cfg.pending_order_timeout_seconds)

    def _cancel_if_timed_out(self, state: BotState) -> None:
        pending = state.pending
        if pending is None:
            return
        limit = self._pending_limit(pending)
        if limit <= 0 or pending.placed_at <= 0:
            return
        if time.time() - pending.placed_at < limit:
            return
        slog(
            "ORDER_STATUS",
            "pending timeout",
            order_id=pending.order_id,
            side=pending.side,
            limit_sec=limit,
        )
        if not self.cfg.may_place_live_orders:
            state.pending = None
            return
        executor = OrderExecutor(self.cfg, self._rest())
        if not executor.cancel(pending.order_id):
            slog("ERROR", "cancel failed; keeping pending", order_id=pending.order_id)
            return
        refreshed = executor.poll(pending.order_id, pending.amount)
        if refreshed.ok:
            self._book_pending_delta(state, pending, refreshed)
            state.pending = None
        else:
            slog("ERROR", "poll after cancel failed; keeping pending", order_id=pending.order_id)

    def _quote_is_stale(self) -> bool:
        if self.last_quote_ms <= 0:
            return False
        age = time.time() - (self.last_quote_ms / 1000.0)
        return age > float(self.cfg.quote_max_age_sec)

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
            slog("ORDER_STATUS", "order canceled; pending cleared", order_id=result.order_id)
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
                placed_at=time.time(),
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
        )
        fee = self._fill_fee(signal, actual_jpy)
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
                    fees_jpy=state.position.fees_jpy + fee,
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
                    fees_jpy=fee,
                )
        elif signal.side == "sell" and state.position:
            pos_amt = state.position.amount
            if pos_amt <= ZERO or result.executed_amount >= pos_amt:
                pnl = (actual_jpy - fee) - state.position.actual_execution_jpy - state.position.fees_jpy
                state.risk.record_realized_pnl(pnl)
                state.position = None
            else:
                frac = result.executed_amount / pos_amt
                cost = state.position.actual_execution_jpy * frac
                allocated = state.position.fees_jpy * frac
                state.risk.record_realized_pnl((actual_jpy - fee) - cost - allocated)
                state.position.amount = pos_amt - result.executed_amount
                state.position.actual_execution_jpy -= cost
                state.position.fees_jpy -= allocated
        if result.reason == "partial_fill" and result.order_id:
            already = ZERO
            placed_at = time.time()
            kept_avg = result.average_price
            if state.pending is not None and state.pending.order_id == result.order_id:
                already = state.pending.filled_amount
                placed_at = state.pending.placed_at or placed_at
                if kept_avg <= ZERO:
                    kept_avg = state.pending.average_price
            state.pending = PendingOrder(
                order_id=result.order_id,
                side=signal.side or "",
                kind=signal.kind,
                tp_pct=signal.tp_pct,
                index=index,
                timestamp_ms=ts,
                amount=plan.amount,
                filled_amount=already + result.executed_amount,
                placed_at=placed_at,
                average_price=kept_avg,
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
        else:
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
                    wait = float(self.cfg.poll_sec)
                    if state.pending is not None and state.pending.side == "sell":
                        wait = min(wait, float(self.cfg.exit_poll_sec))
                    for _ in range(int(max(1, wait))):
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
        slog("HEARTBEAT", "REST API ERROR" if self.last_error else "REST API OK")
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
            stamp = ticker.get("timestamp")
            if stamp not in (None, ""):
                self.last_quote_ms = int(stamp)
        except Exception as exc:
            self.last_error = type(exc).__name__

    def _fill_fee(self, signal: Signal, notional: Decimal) -> Decimal:
        rate = self.cfg.taker_fee_rate
        if signal.kind != "STOP" and self.cfg.post_only and self.cfg.order_type == "limit":
            rate = self.cfg.maker_fee_rate
        return fill_fee_jpy(notional, rate)

    def _buy_guard_allows(self, signal: Signal, state: BotState) -> bool:
        if self._returns:
            posterior = probability_state_updater(self._returns)
            entropy = shannon_entropy(self._returns)
            down = posterior["down"]
            self.posterior_up = posterior["up"]
            self.posterior_down = down
            self.entropy = entropy
        else:
            entropy = ZERO
            down = D("0.333")
        halt = state.risk.halt_reason() in {
            "daily_pnl_floor",
            "max_daily_loss",
            "daily_profit_target",
        }
        allowed, why = self_healing_execution_guard(
            side="buy",
            kind=signal.kind,
            tp_pct=signal.tp_pct if signal.tp_pct is not None else self.cfg.buy1_tp,
            fee_rate=self.cfg.taker_fee_rate,
            entropy=entropy,
            samples=len(self._returns),
            posterior_down=down,
            daily_halt=halt,
        )
        if not allowed:
            self.last_block_reason = why
            slog("RISK", "buy blocked by execution guard", reason=why)
        return allowed

    def _observe_close(self, close: Decimal) -> None:
        close = D(close)
        if self._closes and self._closes[-1] == close:
            return
        prev = self._closes[-1] if self._closes else None
        self._closes.append(close)
        if len(self._closes) > 64:
            del self._closes[:-64]
        if prev is not None and prev > ZERO:
            self._returns.append((close - prev) / prev)
            if len(self._returns) > 64:
                del self._returns[:-64]
            posterior = probability_state_updater(self._returns)
            self.entropy = shannon_entropy(self._returns)
            self.posterior_up = posterior["up"]
            self.posterior_down = posterior["down"]
        self.spline_slope = spline_end_slope(self._closes)

    def _note_scenarios(self, price: Decimal) -> None:
        try:
            lot = self.cfg.fixed_order_btc if self.cfg.fixed_order_btc > ZERO else D("0.001")
            self.scenarios = multi_scenario_inference(lot, price, self.cfg.taker_fee_rate)
        except Exception as exc:
            slog("ERROR", "scenario note skipped", error=type(exc).__name__)

    def _mark_price(self) -> Decimal | None:
        if self.last_quote_ms <= 0 or self.last_public_last in {"", "-"}:
            return None
        try:
            price = D(self.last_public_last)
        except Exception:
            return None
        if price <= ZERO:
            return None
        return price

    def _protective_exit(self, state: BotState, index: int, ts: int) -> Signal | None:
        if state.pending is not None or state.position is None:
            return None
        mark = self._mark_price()
        if mark is None or self._quote_is_stale():
            return None
        pos = state.position
        signal: Signal | None = None
        order_type: str | None = None
        price = mark
        if self.cfg.stop_loss_pct > ZERO and mark <= pos.average_price * (ONE - self.cfg.stop_loss_pct):
            signal = Signal("STOP", "sell", pos.tp_pct, "live_mark_stop")
            order_type = self.cfg.stop_order_type
        elif pos.tp_pct > ZERO and mark >= pos.average_price * (ONE + pos.tp_pct):
            signal = Signal("TP", "sell", pos.tp_pct, "live_mark_tp")
            order_type = "limit"
            price = pos.average_price * (ONE + pos.tp_pct)
        if signal is None:
            return None
        slog("STRATEGY", "protective exit", kind=signal.kind, mark=str(mark))
        self._execute(signal, price, index, ts, state, order_type=order_type)
        return signal

    def _entropy_text(self) -> str:
        if len(self._returns) < 8:
            return "-"
        return f"{shannon_entropy(self._returns):.3f}"

    def _posterior_text(self) -> str:
        if len(self._returns) < 8:
            return "-"
        return f"{self.posterior_up:.3f}"

    def reconcile(self, state: BotState) -> None:
        if not self.cfg.has_keys or self._explicit_synthetic:
            return
        try:
            self._reconcile_open(state)
        except Exception as exc:
            slog("ERROR", "reconcile skipped", error=type(exc).__name__)

    def _reconcile_open(self, state: BotState) -> None:
        rest = self._rest()
        active = rest.get_active_orders(self.cfg.pair) or []
        ids = [str(row.get("order_id")) for row in active if row.get("order_id")]
        local = state.pending.order_id if state.pending else None
        status: str | None = None
        if local and local not in ids:
            try:
                row = rest.get_order(self.cfg.pair, local)
                status = str((row or {}).get("status") or "")
            except Exception:
                status = None
        decision = decide_reconcile(local, ids, status)
        slog("ORDER_STATUS", "reconcile", action=decision.action, reason=decision.reason)
        if decision.action == "clear":
            state.pending = None
        elif decision.action == "adopt" and state.pending is None and decision.order_id:
            chosen = next(row for row in active if str(row.get("order_id")) == decision.order_id)
            state.pending = PendingOrder(
                order_id=decision.order_id,
                side=str(chosen.get("side") or ""),
                kind="RECONCILE",
                tp_pct=None,
                index=0,
                timestamp_ms=0,
                amount=D(chosen.get("start_amount") or chosen.get("remaining_amount") or 0),
                filled_amount=D(chosen.get("executed_amount") or 0),
                placed_at=time.time(),
                average_price=D(chosen.get("average_price") or 0),
            )
            slog(
                "ORDER_STATUS",
                "adopted exchange order; not placing another",
                order_id=decision.order_id,
            )
        if state.position is None:
            return
        try:
            free = D(rest.free_amount("btc"))
        except Exception as exc:
            slog("ERROR", "reconcile balance skipped", error=type(exc).__name__)
            return
        if free != state.position.amount:
            slog(
                "ASSET",
                "btc free differs from tracked position; not selling the difference",
                free=str(free),
                position=str(state.position.amount),
            )

    def _paint(self, state: BotState, signal: Signal, last: str = "-") -> None:
        self.hold_escape = gravity_well_escape_optimizer(
            in_position=state.position is not None,
            signal_kind=signal.kind,
            block_reason=self.last_block_reason,
            samples=len(self._returns),
        )
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
            daily_pnl=state.risk.daily_pnl,
            entropy=self._entropy_text(),
            posterior_up=self._posterior_text(),
            escape=self.hold_escape,
            fee_note="往復テイカー約0.24%。0.05%の小幅は費用負け",
        )
        self.screen.render(view)


def install_signal_handlers(engine: Engine) -> None:
    signal.signal(signal.SIGTERM, engine.request_stop)
    signal.signal(signal.SIGINT, engine.request_stop)
