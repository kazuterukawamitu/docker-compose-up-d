"""Max position, max loss, stop-loss, trailing stop, take-profit cap."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from bitbank_bot.config import Settings
from bitbank_bot.models import Position, Side, Signal, Ticker


@dataclass(frozen=True, slots=True)
class RiskDecision:
    allowed: bool
    reason: str
    signal: Signal


class RiskManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.realized_pnl = Decimal("0")
        self.starting_equity: Decimal | None = None

    def note_equity(self, jpy: Decimal, btc: Decimal, price: Decimal) -> None:
        equity = jpy + btc * price
        if self.starting_equity is None:
            self.starting_equity = equity

    def max_loss_hit(self, jpy: Decimal, btc: Decimal, price: Decimal) -> bool:
        if self.starting_equity is None or self.starting_equity <= 0:
            return False
        equity = jpy + btc * price
        drawdown = (self.starting_equity - equity) / self.starting_equity
        return drawdown >= self._settings.max_loss_fraction

    def approve(
        self,
        signal: Signal,
        position: Position,
        ticker: Ticker,
        jpy_free: Decimal,
        btc_free: Decimal,
    ) -> RiskDecision:
        price = ticker.last
        self.note_equity(jpy_free, btc_free, price)
        if self.max_loss_hit(jpy_free, btc_free, price):
            if position.is_open:
                forced = Signal(Side.SELL, "max loss flatten", size_mode="all")
                return RiskDecision(True, "max loss: flatten", forced)
            return RiskDecision(False, "max loss: halt new entries", Signal.hold("max loss"))

        protective = self.protective_exit(position, price)
        if protective is not None:
            return RiskDecision(True, protective.reason, protective)

        if signal.side is None:
            return RiskDecision(False, signal.reason, signal)

        if signal.side is Side.BUY:
            if position.is_open:
                return RiskDecision(False, "already in position", Signal.hold("already long"))
            if btc_free + self._settings.min_order_btc > self._settings.max_position_btc:
                return RiskDecision(False, "max position reached", Signal.hold("max position"))
            return RiskDecision(True, signal.reason, signal)

        if not position.is_open and btc_free < self._settings.min_order_btc:
            return RiskDecision(False, "no BTC to sell", Signal.hold("flat"))
        return RiskDecision(True, signal.reason, signal)

    def protective_exit(self, position: Position, price: Decimal) -> Signal | None:
        if not position.is_open or position.entry_price is None:
            return None
        entry = position.entry_price
        if position.high_water is None or price > position.high_water:
            position.high_water = price

        stop = entry * (Decimal("1") - self._settings.stop_loss_pct)
        if price <= stop:
            return Signal(Side.SELL, "stop-loss", size_mode="all")

        if position.high_water:
            trail = position.high_water * (Decimal("1") - self._settings.trailing_stop_pct)
            if price <= trail and position.high_water > entry:
                return Signal(Side.SELL, "trailing stop", size_mode="all")

        cap = entry * (Decimal("1") + self._settings.take_profit_cap_pct)
        if price >= cap:
            return Signal(Side.SELL, "take-profit cap", size_mode="all")

        if position.take_profit_pct is not None:
            target = entry * (Decimal("1") + position.take_profit_pct)
            if price >= target:
                return Signal(Side.SELL, f"strategy TP {position.take_profit_pct}", size_mode="all")
        return None

    def cap_buy_amount(self, amount: Decimal, current_btc: Decimal) -> Decimal:
        room = self._settings.max_position_btc - current_btc
        if room <= 0:
            return Decimal("0")
        return min(amount, room)
