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

from bitbank_bot.amounts import PositionSizer
from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.market_data import (
    Candle,
    CandleCache,
    drop_incomplete_candle,
    fetch_candles,
    synthetic_candles,
)
from bitbank_bot.money import D, ZERO
from bitbank_bot.orders import OrderExecutor, OrderResult
from bitbank_bot.preflight import preflight
from bitbank_bot.rest_client import BitbankAPIError, RestClient, is_auth_error
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import Position, Signal, Strategy, build_snapshots
from bitbank_bot.websocket_client import BitbankWebsocket

_LOG = logging.getLogger("bitbank_bot")


@dataclass
class BotState:
    position: Position | None
    risk: RiskManager
    last_candle_ts: int
    started_at: float


def load_state(path: str | Path, cfg: Config) -> BotState:
    risk = RiskManager(cfg)
    position = None
    last_ts = 0
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
            )
        operator_killed = bool(raw.get("operator_killed", False))
        risk = RiskManager(
            cfg,
            daily_pnl=D(raw.get("daily_pnl") or 0),
            daily_pnl_date=raw.get("daily_pnl_date"),
            killed=operator_killed or cfg.kill_switch,
        )
        last_ts = int(raw.get("last_candle_ts") or 0)
    return BotState(position, risk, last_ts, time.monotonic())


def save_state(path: str | Path, state: BotState) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "daily_pnl": str(state.risk.daily_pnl),
        "daily_pnl_date": state.risk.daily_pnl_date,
        "operator_killed": state.risk.operator_killed,
        "last_candle_ts": state.last_candle_ts,
        "position": None,
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
        }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class Engine:
    def __init__(self, cfg: Config, client: RestClient | None = None) -> None:
        self.cfg = cfg
        self.client = client
        self._stop = False
        self.ws: BitbankWebsocket | None = None
        self.cache = CandleCache(cfg.ma_period)
        self.last_block_reason = ""
        self.strategy_evaluations = 0
        self.cycles = 0
        self.used_synthetic_fallback = False
        self.last_watchdog = ""

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

    def _balances(self, rest: RestClient) -> tuple[Decimal, Decimal]:
        if self.cfg.has_keys:
            jpy = rest.free_amount("jpy")
            btc = rest.free_amount("btc")
            slog("ASSET", "free_amount", jpy=str(jpy), btc=str(btc))
            return jpy, btc
        return self.cfg.dry_run_free_jpy, self.cfg.dry_run_free_btc

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
            return Signal.hold("not_enough_candles")
        strategy = Strategy(self.cfg)
        last = snaps[-1]
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
            slog("STRATEGY", "signal", kind=signal.kind, reason=signal.reason, side=signal.side)
            if not execute or heartbeat:
                if heartbeat:
                    slog("STRATEGY", "candle already processed", candle_ts=snap.timestamp_ms)
                continue
            if signal.side in {"buy", "sell"}:
                if self.ws is not None and self.cfg.enable_websocket and self.ws.is_stale():
                    slog("WEBSOCKET", "stale data; skipping orders")
                    self.last_block_reason = "stale_websocket"
                    signal = Signal.hold("stale_websocket")
                    break
                self._execute(signal, snap.close, snap.index, snap.timestamp_ms, state)
            state.last_candle_ts = snap.timestamp_ms
            if persist:
                save_state(self.cfg.state_path, state)
        return signal

    def _execute(
        self,
        signal: Signal,
        price: Decimal,
        index: int,
        ts: int,
        state: BotState,
    ) -> None:
        rest = self._rest()
        if self.ws is not None and not self.ws.is_stale() and self.ws.last_price():
            price = self.ws.last_price() or price
        try:
            jpy, btc = self._balances(rest)
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
        if signal.side == "buy":
            tp = signal.tp_pct if signal.tp_pct is not None else self.cfg.buy1_tp
            state.position = Position(
                amount=result.executed_amount,
                average_price=result.average_price,
                tp_pct=tp,
                entry_candle_index=index,
                entry_candle_ts=ts,
                actual_execution_jpy=actual_jpy,
                kind=signal.kind,
            )
        elif signal.side == "sell" and state.position:
            pnl = actual_jpy - state.position.actual_execution_jpy
            state.risk.record_realized_pnl(pnl)
            state.position = None

    def run_once(self, *, synthetic: bool = False, skip_preflight: bool = False) -> int:
        slog("BOOT", "run_once", synthetic=synthetic, dry_run=self.cfg.dry_run)
        rest = self._rest()
        if not skip_preflight and not synthetic:
            result = preflight(self.cfg, rest, require_public=True)
            if not result.ok:
                slog("ERROR", "preflight failed", reason=result.reason)
                return 2
        candles = synthetic_candles() if synthetic else fetch_candles(rest, self.cfg)
        if synthetic:
            slog("MARKET", "using synthetic candles", count=len(candles))
            state = BotState(None, RiskManager(self.cfg), 0, time.monotonic())
        else:
            candles = self.cache.merge(candles)
            state = load_state(self.cfg.state_path, self.cfg)
        signal = self.process_candles(
            candles, state, execute=True, persist=not synthetic
        )
        last = str(candles[-1].close) if candles else "-"
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
            slog("WATCHDOG", "NORMAL WAIT", reason="empty_public_candles")
            self.last_watchdog = "NORMAL WAIT"
        except Exception as exc:
            slog(
                "WATCHDOG",
                "FAIL",
                reason="public_candles_failed_using_synthetic",
                error=type(exc).__name__,
            )
            self.last_watchdog = "FAIL"
        self.used_synthetic_fallback = True
        slog("MARKET", "synthetic fallback; loop continues")
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
        rest = self._rest()
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
        last_ok = time.monotonic()
        timeout = float(self.cfg.no_trade_timeout_seconds)
        while not self._stop:
            try:
                latest_only = bool(self.cache.candles) and not synthetic
                incoming = self._candles_for_cycle(
                    rest, latest_only=latest_only, force_synthetic=synthetic
                )
                candles = self.cache.merge(incoming)
                signal = self.process_candles(
                    candles,
                    state,
                    execute=True,
                    persist=not (synthetic or self.used_synthetic_fallback),
                )
                last_ok = time.monotonic()
                last = str(candles[-1].close) if candles else "-"
                self._heartbeat(state, signal, last)
                if signal.kind == "HOLD" or signal.side is None:
                    slog(
                        "WATCHDOG",
                        "NORMAL WAIT",
                        reason=signal.reason,
                        kind=signal.kind,
                    )
                    self.last_watchdog = "NORMAL WAIT"
                self.cycles += 1
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


def install_signal_handlers(engine: Engine) -> None:
    signal.signal(signal.SIGTERM, engine.request_stop)
    signal.signal(signal.SIGINT, engine.request_stop)
