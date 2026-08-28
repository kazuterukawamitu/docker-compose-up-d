"""Main trading loop. Default path is dry-run and never POSTs live orders."""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from bitbank_bot.config import Settings
from bitbank_bot.dashboard import Dashboard
from bitbank_bot.exceptions import InsufficientFundsError
from bitbank_bot.exchange.rest import BitbankRest
from bitbank_bot.market.candles import MarketData
from bitbank_bot.ml.predictor import Predictor
from bitbank_bot.models import Side, Signal, Ticker
from bitbank_bot.orders.amount import buyable_btc, sellable_btc
from bitbank_bot.orders.manager import OrderManager
from bitbank_bot.orders.repository import JsonRepository
from bitbank_bot.preflight import run_preflight
from bitbank_bot.risk.manager import RiskManager
from bitbank_bot.strategy.plugins import build_strategies

log = logging.getLogger("bitbank_bot.trader")

DRY_JPY = Decimal("1000000")


class Trader:
    def __init__(self, settings: Settings, rest: BitbankRest) -> None:
        self._settings = settings
        self._rest = rest
        self._market = MarketData(settings, rest)
        self._strategy = build_strategies(settings)
        self._risk = RiskManager(settings)
        self._orders = OrderManager(settings, rest, JsonRepository(settings.data_dir))
        self._dash = Dashboard(settings)
        self._ml = Predictor(settings.ml_enabled, settings.ml_model_path)
        self._latest_ticker: Ticker | None = None
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def on_ticker(self, ticker: Ticker) -> None:
        self._latest_ticker = ticker

    async def run(self) -> None:
        report = await run_preflight(self._settings, self._rest)
        log.info("starting trader dry_run=%s preflight=%s", self._settings.dry_run, report)
        while not self._stop.is_set():
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("tick failed; will retry")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._settings.loop_seconds)
            except TimeoutError:
                pass

    async def _tick(self) -> None:
        ticker = self._latest_ticker or await self._rest.get_ticker()
        snapshot = await self._market.refresh(ticker)
        jpy, btc = await self._balances(ticker.last)
        signal = self._strategy.evaluate(snapshot)
        bias = self._ml.bias(snapshot)
        if bias == "sell" and signal.side is Side.BUY:
            signal = Signal.hold("ML vetoed buy")
        decision = self._risk.approve(signal, self._orders.position, ticker, jpy, btc)
        note = decision.reason
        if decision.allowed and decision.signal.side is not None:
            try:
                await self._execute(decision.signal, ticker, jpy, btc)
                note = f"executed {decision.signal.reason}"
            except InsufficientFundsError as exc:
                note = str(exc)
                log.info("skip order: %s", exc)
        self._dash.render(snapshot, self._orders.position, decision.signal, jpy, btc, note)

    async def _execute(self, signal: Signal, ticker: Ticker, jpy: Decimal, btc: Decimal) -> None:
        if signal.side is Side.BUY:
            amount = buyable_btc(jpy, ticker.last, self._settings)
            amount = self._risk.cap_buy_amount(amount, btc)
            await self._orders.submit(
                side=Side.BUY,
                amount_btc=amount,
                ticker=ticker,
                jpy_free=jpy,
                btc_free=btc,
                reason=signal.reason,
                take_profit_pct=signal.take_profit_pct,
            )
            return
        amount = sellable_btc(btc if btc > 0 else self._orders.position.amount_btc, self._settings)
        await self._orders.submit(
            side=Side.SELL,
            amount_btc=amount,
            ticker=ticker,
            jpy_free=jpy,
            btc_free=max(btc, self._orders.position.amount_btc),
            reason=signal.reason,
        )

    async def _balances(self, last: Decimal) -> tuple[Decimal, Decimal]:
        if self._settings.dry_run:
            pos = self._orders.position
            if pos.is_open:
                return DRY_JPY, pos.amount_btc
            # Compounding: after a dry-run round trip, keep simulated JPY constant unless we track fills.
            return DRY_JPY, Decimal("0")
        jpy, btc = await self._rest.get_balances()
        return jpy.free, btc.free
