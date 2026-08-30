"""Main loop: candles → strategy → risk → amounts → orders."""

from __future__ import annotations

import json
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from bitbank_bot.amounts import AmountPlan, PositionSizer
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
from bitbank_bot.multi_timeframe import TimeframeHealth, higher_tf_ready, load_all_timeframes
from bitbank_bot.orders import OrderExecutor, OrderResult
from bitbank_bot.preflight import preflight
from bitbank_bot.rest_client import RestClient
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import Position, Signal, Strategy, build_snapshots
from bitbank_bot.watchdog import WatchInput, diagnose
from bitbank_bot.websocket_client import BitbankWebsocket


@dataclass
class LoopStats:
    started_ms: int
    last_market_data_ms: int = 0
    strategy_evaluations: int = 0
    buy_signals: int = 0
    sell_signals: int = 0
    order_attempts: int = 0
    last_signal_kind: str = "n/a"
    last_signal_reason: str = ""
    last_error: str = ""
    last_block_reason: str = ""


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
        risk = RiskManager(
            cfg,
            daily_pnl=D(raw.get("daily_pnl") or 0),
            daily_pnl_date=raw.get("daily_pnl_date"),
            killed=bool(raw.get("kill_switch", cfg.kill_switch)),
        )
        last_ts = int(raw.get("last_candle_ts") or 0)
    return BotState(position, risk, last_ts, time.monotonic())


def save_state(path: str | Path, state: BotState) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "daily_pnl": str(state.risk.daily_pnl),
        "daily_pnl_date": state.risk.daily_pnl_date,
        "kill_switch": state.risk.killed,
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


def _dashboard(cfg: Config, state: BotState, last: str, signal: Signal) -> None:
    if not cfg.dashboard:
        return
    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        return
    table = Table(title="Bitbank BTC/JPY")
    table.add_column("field")
    table.add_column("value")
    uptime = int(time.monotonic() - state.started_at)
    table.add_row("price", last)
    table.add_row("signal", signal.kind)
    table.add_row("dry_run", str(cfg.dry_run))
    table.add_row("uptime_sec", str(uptime))
    if state.position:
        table.add_row("hold_btc", str(state.position.amount))
        table.add_row("avg_fill", str(state.position.average_price))
        table.add_row("tp_pct", str(state.position.tp_pct))
    else:
        table.add_row("hold_btc", "0")
    Console().print(table)


class Engine:
    def __init__(self, cfg: Config, client: RestClient | None = None) -> None:
        self.cfg = cfg
        self.client = client
        self._stop = False
        self.ws: BitbankWebsocket | None = None
        self.cache = CandleCache(cfg.ma_period)
        self.stats = LoopStats(started_ms=int(time.time() * 1000))
        self.mtf_health: dict[str, TimeframeHealth] = {}
        self._mtf_cycles = 0

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
        self.ws = BitbankWebsocket(
            self.cfg.ws_url, self.cfg.ws_rooms, stale_sec=self.cfg.stale_ws_sec
        )
        self.ws.start()

    def process_candles(
        self,
        candles: list[Candle],
        state: BotState,
        execute: bool,
    ) -> Signal:
        candles = drop_incomplete_candle(candles, self.cfg.candle_type)
        if candles:
            self.stats.last_market_data_ms = candles[-1].timestamp_ms
        closes = [c.close for c in candles]
        stamps = [c.timestamp_ms for c in candles]
        snaps = build_snapshots(closes, stamps, self.cfg)
        if not snaps:
            slog("STRATEGY", "not enough candles for MA")
            return Signal.hold("not_enough_candles")
        strategy = Strategy(self.cfg)
        for snap in snaps[:-1]:
            strategy.observe(snap)
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
        signal = strategy.evaluate(last, state.position)
        self.stats.strategy_evaluations += 1
        self.stats.last_signal_kind = signal.kind
        self.stats.last_signal_reason = signal.reason
        if signal.side == "buy":
            self.stats.buy_signals += 1
        elif signal.side == "sell":
            self.stats.sell_signals += 1
        slog("SIGNAL", signal.kind, reason=signal.reason, side=signal.side or "-")
        if (
            signal.side == "buy"
            and self.cfg.mtf_filter
            and self.mtf_health
        ):
            allowed, reason = higher_tf_ready(self.mtf_health)
            if not allowed:
                self.stats.last_block_reason = reason
                slog("STRATEGY", "mtf filter blocked buy", reason=reason)
                signal = Signal.hold(reason)
        if not execute:
            return signal
        if last.timestamp_ms == state.last_candle_ts:
            slog("STRATEGY", "candle already processed", ts=last.timestamp_ms)
            return signal
        if self.ws is not None and self.cfg.enable_websocket and self.ws.is_stale():
            slog("WEBSOCKET", "stale data; skipping orders")
            return Signal.hold("stale_websocket")
        if signal.side in {"buy", "sell"}:
            self._execute(signal, last.close, last.index, last.timestamp_ms, state)
        state.last_candle_ts = last.timestamp_ms
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
        jpy, btc = self._balances(rest)
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
            self.stats.last_block_reason = plan.reason
            return
        self.stats.order_attempts += 1
        order_client = rest if self.cfg.has_keys else None
        executor = OrderExecutor(self.cfg, order_client)
        result = executor.place(signal, plan)
        slog("HEARTBEAT", "ORDER MANAGER OK", reason=result.reason, simulated=result.simulated)
        self._apply_fill(signal, plan, result, index, ts, state, jpy, btc)

    def _apply_fill(
        self,
        signal: Signal,
        plan: AmountPlan,
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
        if not synthetic:
            candles = self.cache.merge(candles)
            if self.cfg.mtf_health:
                self.mtf_health = load_all_timeframes(rest, self.cfg)
        if synthetic:
            slog("MARKET", "using synthetic candles", count=len(candles))
        state = load_state(self.cfg.state_path, self.cfg)
        signal = self.process_candles(candles, state, execute=True)
        last = str(candles[-1].close) if candles else "-"
        self._heartbeat(state, signal, last)
        slog("BOOT", "run_once complete")
        return 0

    def run_forever(self) -> int:
        slog("BOOT", "run_forever", pair=self.cfg.pair)
        rest = self._rest()
        result = preflight(self.cfg, rest, require_public=True)
        if not result.ok:
            slog("ERROR", "preflight failed", reason=result.reason)
            return 2
        if self.cfg.enable_websocket:
            self._maybe_ws()
        state = load_state(self.cfg.state_path, self.cfg)
        last_ok = time.monotonic()
        timeout = float(self.cfg.no_trade_timeout_seconds)
        while not self._stop:
            try:
                latest_only = bool(self.cache.candles)
                incoming = fetch_candles(rest, self.cfg, latest_only=latest_only)
                candles = self.cache.merge(incoming)
                self._mtf_cycles += 1
                if self.cfg.mtf_health and (not latest_only or self._mtf_cycles % 20 == 0):
                    self.mtf_health = load_all_timeframes(rest, self.cfg)
                signal = self.process_candles(candles, state, execute=True)
                last_ok = time.monotonic()
                last = str(candles[-1].close) if candles else "-"
                self._heartbeat(state, signal, last)
                self._watchdog()
                _dashboard(self.cfg, state, last, signal)
            except Exception as exc:
                self.stats.last_error = type(exc).__name__
                slog("ERROR", "loop error", error=type(exc).__name__, detail=str(exc)[:200])
                if time.monotonic() - last_ok >= timeout:
                    slog("WATCHDOG", "FAIL stuck loop", idle_sec=int(time.monotonic() - last_ok))
                    break
            for _ in range(int(max(1, self.cfg.poll_sec))):
                if self._stop:
                    break
                time.sleep(1)
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

    def _watchdog(self) -> None:
        now_ms = int(time.time() * 1000)
        status, reason = diagnose(
            WatchInput(
                now_ms=now_ms,
                started_ms=self.stats.started_ms,
                timeout_ms=self.cfg.no_trade_timeout_seconds * 1000,
                stale_ms=int(self.cfg.stale_ws_sec * 1000),
                last_market_data_ms=self.stats.last_market_data_ms,
                strategy_evaluations=self.stats.strategy_evaluations,
                buy_signals=self.stats.buy_signals,
                sell_signals=self.stats.sell_signals,
                order_attempts=self.stats.order_attempts,
                last_signal_kind=self.stats.last_signal_kind,
                last_signal_reason=self.stats.last_signal_reason,
                last_error=self.stats.last_error,
                last_block_reason=self.stats.last_block_reason,
                ws_ok=bool(self.ws and self.ws.is_connected()),
            )
        )
        slog("WATCHDOG", status, reason=reason)


def install_signal_handlers(engine: Engine) -> None:
    signal.signal(signal.SIGTERM, engine.request_stop)
    signal.signal(signal.SIGINT, engine.request_stop)
