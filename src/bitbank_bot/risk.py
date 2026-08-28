"""Kill switch, max position, and daily loss caps."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO

JST = timezone(timedelta(hours=9))


def jst_today() -> date:
    return datetime.now(JST).date()


@dataclass
class RiskDecision:
    allowed: bool
    capped_btc: Decimal
    reason: str
    killed: bool


class RiskManager:
    def __init__(
        self,
        cfg: Config,
        daily_pnl: Decimal = ZERO,
        daily_pnl_date: str | None = None,
        killed: bool | None = None,
    ) -> None:
        self.cfg = cfg
        self.max_position_btc = cfg.max_position_btc
        self.max_order_btc = cfg.max_order_btc
        self.max_daily_loss_jpy = cfg.max_daily_loss_jpy
        self.daily_pnl = D(daily_pnl)
        self.daily_pnl_date = daily_pnl_date or jst_today().isoformat()
        self._killed = cfg.kill_switch if killed is None else bool(killed)

    def _roll_day(self) -> None:
        today = jst_today().isoformat()
        if today != self.daily_pnl_date:
            self.daily_pnl = ZERO
            self.daily_pnl_date = today

    @property
    def killed(self) -> bool:
        self._roll_day()
        if self._killed:
            return True
        if self.max_daily_loss_jpy > ZERO and self.daily_pnl <= -self.max_daily_loss_jpy:
            return True
        return False

    def trip(self, reason: str) -> None:
        self._killed = True
        slog("RISK", "kill switch tripped", reason=reason)

    def record_realized_pnl(self, pnl_jpy: Decimal) -> None:
        self._roll_day()
        self.daily_pnl += D(pnl_jpy)
        slog("RISK", "realized pnl", pnl=str(pnl_jpy), daily_pnl=str(self.daily_pnl))
        if self.max_daily_loss_jpy > ZERO and self.daily_pnl <= -self.max_daily_loss_jpy:
            self.trip("max_daily_loss")

    def check_buy(self, current_btc: Decimal, requested_btc: Decimal) -> RiskDecision:
        if self.killed:
            return RiskDecision(False, ZERO, "kill_switch", True)
        headroom = self.max_position_btc - D(current_btc)
        if headroom <= ZERO:
            return RiskDecision(False, ZERO, "max_position", False)
        capped = min(D(requested_btc), headroom, self.max_order_btc)
        if capped <= ZERO:
            return RiskDecision(False, ZERO, "capped_to_zero", False)
        return RiskDecision(True, capped, "ok", False)

    def check_sell(self, requested_btc: Decimal) -> RiskDecision:
        if self.killed and self.cfg.kill_switch:
            return RiskDecision(False, ZERO, "kill_switch", True)
        capped = min(D(requested_btc), self.max_order_btc)
        return RiskDecision(True, capped, "ok", self.killed)
