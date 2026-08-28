from __future__ import annotations

import asyncio
import logging
import signal
import time
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from bitbank_bot.config import Settings
from bitbank_bot.dashboard import render_status
from bitbank_bot.exceptions import BotError, ExchangeError, RiskBlocked
from bitbank_bot.exchange.bitbank_rest import BitbankRest
from bitbank_bot.exchange.bitbank_ws import BitbankPublicWS
from bitbank_bot.instance_lock import InstanceLock
from bitbank_bot.logging_setup import log_event
from bitbank_bot.market.cache import MarketCache
from bitbank_bot.models import BotStats, Snapshot, Ticker
from bitbank_bot.orders.manager import OrderManager
from bitbank_bot.orders.sizing import plan_size
from bitbank_bot.orders.states import apply_fill, load_position, save_position
from bitbank_bot.risk.manager import RiskManager
from bitbank_bot.strategy.ma_rules import MaRuleStrategy
from bitbank_bot.watchdog import diagnose, from_stats

log = logging.getLogger(__name__)
JST = ZoneInfo("Asia/Tokyo")


class TradingBot:
    def __init__(self, settings: Settings, rest: BitbankRest | None = None) -> None:
        self.settings = settings
        self.cache = MarketCache()
        self.rest = rest
        self.owns_rest = rest is None
        self.strategy = MaRuleStrategy(settings)
        self.risk = RiskManager(settings)
        self.orders = OrderManager(settings, client=None)
        self.position = load_position(settings.state_dir / "position.json")
        self.stats = BotStats(started_ms=_now_ms())
        self._stop = asyncio.Event()
        self._ws: BitbankPublicWS | None = None
        self._day_key = _jst_day()
        self._paper_jpy = Decimal("1000000")
        self._paper_btc = Decimal("0")

    def request_stop(self) -> None:
        self._stop.set()
        if self._ws is not None:
            self._ws.stop()

    async def run(self, once: bool = False) -> None:
        settings = self.settings
        settings.state_dir.mkdir(parents=True, exist_ok=True)
        lock = InstanceLock(settings.state_dir / "bot.lock")
        lock.acquire()
        try:
            if self.rest is None:
                self.rest = BitbankRest(settings)
                await self.rest.__aenter__()
            self.orders.client = None if settings.dry_run else self.rest
            await self._bootstrap_market()
            ws_task = asyncio.create_task(self._run_ws(), name="bitbank-ws")
            try:
                while not self._stop.is_set():
                    await self.cycle()
                    if once:
                        break
                    try:
                        await asyncio.wait_for(self._stop.wait(), timeout=settings.loop_seconds)
                    except TimeoutError:
                        pass
            finally:
                self.request_stop()
                ws_task.cancel()
                try:
                    await ws_task
                except asyncio.CancelledError:
                    pass
        finally:
            if self.owns_rest and self.rest is not None:
                await self.rest.close()
            lock.release()

    async def _run_ws(self) -> None:
        self._ws = BitbankPublicWS(self.settings, self.cache)
        await self._ws.run()

    async def _bootstrap_market(self) -> None:
        assert self.rest is not None
        min_bars = max(self.settings.ema_slow + self.settings.slope_lookback + 5, 60)
        candles = await self.rest.fetch_candles(self.settings.pair, self.settings.candle_type, min_bars)
        self.cache.set_candles(candles)
        ticker = await self.rest.fetch_ticker(self.settings.pair)
        self.cache.upsert_ticker(ticker, source="rest")
        try:
            self.cache.circuit_mode = await self.rest.fetch_circuit_break(self.settings.pair)
        except ExchangeError:
            log.exception("circuit_break_info unavailable")
        self.stats.last_market_data_ms = _now_ms()
        log.info("bootstrapped %s candles last=%s", len(candles), ticker.last)

    async def cycle(self) -> None:
        assert self.rest is not None
        self._roll_day()
        snapshot: Snapshot | None = None
        try:
            min_bars = max(self.settings.ema_slow + self.settings.slope_lookback + 5, 60)
            if len(self.cache.candles) < min_bars:
                self.cache.set_candles(
                    await self.rest.fetch_candles(self.settings.pair, self.settings.candle_type, min_bars)
                )
            else:
                latest = await self.rest.fetch_candles(self.settings.pair, self.settings.candle_type, 24)
                if latest:
                    merged = {c.ts: c for c in self.cache.candles}
                    for candle in latest:
                        merged[candle.ts] = candle
                    self.cache.set_candles(sorted(merged.values(), key=lambda c: c.ts)[-500:])
            if not self.cache.ws_connected or self.cache.age_ms() is None or (self.cache.age_ms() or 0) > self.settings.stale_ms:
                ticker = await self.rest.fetch_ticker(self.settings.pair)
                self.cache.upsert_ticker(ticker, source="rest")
            try:
                self.cache.circuit_mode = await self.rest.fetch_circuit_break(self.settings.pair)
            except ExchangeError:
                log.exception("circuit_break_info refresh failed")
            self.stats.last_market_data_ms = _now_ms()
            jpy_free, btc_free = await self._balances()
            snapshot = self._snapshot(jpy_free, btc_free)
            signal = self.strategy.evaluate(
                snapshot.candles,
                self.position,
                live_price=snapshot.ticker.last,
            )
            self.stats.strategy_evaluations += 1
            self.stats.last_signal = signal
            self.stats.signals_seen += 1
            if signal.action == "BUY":
                self.stats.buy_signals += 1
            elif signal.action == "SELL":
                self.stats.sell_signals += 1
            log_event(
                "SIGNAL",
                action=signal.action,
                rule=signal.rule_id,
                reason=signal.reason,
                last=snapshot.ticker.last,
                dry_run=self.settings.dry_run,
            )
            if signal.action == "HOLD":
                return
            decision = self.risk.check(signal, snapshot, self.stats.daily_realized_pnl, self.stats.realized_pnl)
            if not decision.allowed:
                self.stats.last_block_reason = decision.reason
                log_event("RISK", result="BLOCKED", action=signal.action, reason=decision.reason)
                return
            plan = plan_size(self.settings, signal, snapshot)
            if plan.planned <= 0:
                self.stats.last_block_reason = plan.blocked
                log_event("ORDER_REQUEST", result="BLOCKED", reason=plan.blocked, action=signal.action)
                return
            self.stats.order_attempts += 1
            side = "buy" if signal.action == "BUY" else "sell"
            log_event(
                "ORDER_REQUEST",
                side=side,
                amount=plan.planned,
                price=plan.price,
                dry_run=self.settings.dry_run,
                rule=signal.rule_id,
            )
            record = await self.orders.submit(
                side,
                plan,
                signal.reason,
                snapshot.ticker.last,
            )
            if record.executed_amount > 0 and record.average_price is not None:
                pnl = apply_fill(
                    self.position,
                    record.side,
                    record.executed_amount,
                    record.average_price,
                    snapshot.now_ms,
                    signal.take_profit_pct,
                    signal.rule_id,
                )
                if record.side == "buy":
                    self.stats.buys += 1
                    if self.settings.dry_run:
                        cost = record.executed_amount * record.average_price
                        self._paper_jpy -= cost
                        self._paper_btc += record.executed_amount
                else:
                    self.stats.sells += 1
                    self.stats.realized_pnl += pnl
                    self.stats.daily_realized_pnl += pnl
                    if pnl >= 0:
                        self.stats.wins += 1
                    else:
                        self.stats.losses += 1
                    if self.settings.dry_run:
                        self._paper_btc -= record.executed_amount
                        self._paper_jpy += record.executed_amount * record.average_price
                save_position(self.settings.state_dir / "position.json", self.position)
                self.risk.record_success()
            else:
                log.info("no fill yet status=%s executed=%s", record.status, record.executed_amount)
        except RiskBlocked as exc:
            self.stats.last_block_reason = str(exc)
            log_event("RISK", result="BLOCKED", reason=str(exc))
        except BotError as exc:
            self.stats.last_error = str(exc)
            self.risk.record_failure(exc)
            log.exception("bot error")
        except Exception as exc:
            self.stats.last_error = str(exc)
            self.risk.record_failure(exc)
            log.exception("unexpected error in cycle")
        finally:
            self._heartbeat_and_watch(snapshot)
            if snapshot is not None:
                render_status(self.settings, snapshot, self.stats, self.position)

    def _heartbeat_and_watch(self, snapshot: Snapshot | None) -> None:
        now = _now_ms()
        hb_ms = max(1, int(self.settings.heartbeat_seconds * 1000))
        due = self.stats.last_heartbeat_ms <= 0 or now - self.stats.last_heartbeat_ms >= hb_ms
        ws_ok = snapshot.ws_ok if snapshot is not None else self.cache.ws_connected
        status, reason = diagnose(
            from_stats(
                self.stats,
                now_ms=now,
                timeout_ms=self.settings.no_trade_timeout_seconds * 1000,
                stale_ms=self.settings.stale_ms,
                ws_ok=ws_ok,
            )
        )
        previous = self.stats.last_watch_status
        self.stats.last_watch_status = status
        if due:
            self.stats.last_heartbeat_ms = now
            last = snapshot.ticker.last if snapshot is not None else self.cache.last_price()
            log_event(
                "HEARTBEAT",
                ws="OK" if ws_ok else "DOWN",
                market="OK" if self.stats.last_market_data_ms else "NONE",
                last=last,
                strategy=self.stats.strategy_evaluations,
                buy=self.stats.buy_signals,
                sell=self.stats.sell_signals,
                order=self.stats.order_attempts,
                status=status,
                uptime_s=max(0, now - self.stats.started_ms) // 1000,
            )
        if status in {"FAIL", "LONG_WAIT"} and (due or status != previous):
            log_event("WATCHDOG", status=status, reason=reason)

    async def _balances(self) -> tuple[Decimal, Decimal]:
        if self.settings.dry_run or self.rest is None or not self.settings.api_key:
            jpy = self._paper_jpy
            btc = self._paper_btc if self._paper_btc > 0 else self.position.amount
            return jpy, btc
        assets = await self.rest.fetch_assets()
        jpy = assets["jpy"].free if "jpy" in assets else Decimal("0")
        btc = assets["btc"].free if "btc" in assets else Decimal("0")
        return jpy, btc

    def _snapshot(self, jpy_free: Decimal, btc_free: Decimal) -> Snapshot:
        ticker = self.cache.ticker
        if ticker is None:
            last = self.cache.candles[-1].close if self.cache.candles else Decimal("0")
            ticker = Ticker(last=last, buy=last, sell=last, timestamp_ms=_now_ms())
        return Snapshot(
            candles=self.cache.candles,
            ticker=ticker,
            position=self.position,
            jpy_free=jpy_free,
            btc_free=btc_free,
            circuit_mode=self.cache.circuit_mode,
            ws_ok=self.cache.ws_connected,
            now_ms=_now_ms(),
        )

    def _roll_day(self) -> None:
        today = _jst_day()
        if today != self._day_key:
            self.stats.daily_realized_pnl = Decimal("0")
            self._day_key = today


def _now_ms() -> int:
    return int(time.time() * 1000)


def _jst_day() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def install_signal_handlers(bot: TradingBot) -> None:
    loop = asyncio.get_running_loop()

    def _stop() -> None:
        log.info("shutdown requested")
        bot.request_stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _stop())
