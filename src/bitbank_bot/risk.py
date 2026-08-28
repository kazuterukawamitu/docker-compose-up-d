"""Kill switch, stale data, daily PnL floor, max position, balances."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from bitbank_bot.config import Settings
from bitbank_bot.models import AmountPlan


@dataclass
class RiskDecision:
    allowed: bool
    reason: str


class RiskManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.kill_switch = False
        self.daily_pnl = Decimal("0")
        self.day_key: str | None = None

    def _roll_day(self, now: datetime | None = None) -> None:
        now = now or datetime.now(tz=UTC)
        key = now.astimezone().date().isoformat()
        if self.day_key != key:
            self.day_key = key
            self.daily_pnl = Decimal("0")

    def record_realized_pnl(self, jpy: Decimal, now: datetime | None = None) -> None:
        self._roll_day(now)
        self.daily_pnl += jpy

    def kill_switch_file_on(self) -> bool:
        return Path(self.settings.kill_switch_path).is_file()

    def trip_kill_switch(self, reason: str) -> RiskDecision:
        self.kill_switch = True
        return RiskDecision(False, f"kill_switch:{reason}")

    def check(
        self,
        *,
        stale: bool,
        side: str,
        plan: AmountPlan,
        free_jpy: Decimal,
        free_btc: Decimal,
        now: datetime | None = None,
        halt_status: str | None = None,
    ) -> RiskDecision:
        self._roll_day(now)
        if self.kill_switch or self.kill_switch_file_on():
            return RiskDecision(False, "kill_switch")
        if halt_status == "HALT":
            return self.trip_kill_switch("exchange_halt")
        if stale:
            return RiskDecision(False, "stale_data")
        if self.daily_pnl <= -self.settings.daily_pnl_floor:
            return RiskDecision(
                False,
                f"daily_pnl_floor pnl={self.daily_pnl} floor=-{self.settings.daily_pnl_floor}",
            )
        max_loss = self.settings.max_daily_loss_jpy
        if max_loss is not None and self.daily_pnl <= -max_loss:
            return RiskDecision(False, f"max_daily_loss pnl={self.daily_pnl}")
        if plan.planned_amount <= 0:
            return RiskDecision(False, f"amount_zero:{plan.reason}")
        if side == "buy":
            needed = plan.planned_amount * plan.price
            if free_jpy < needed:
                return RiskDecision(False, "insufficient_jpy_free_amount")
        elif side == "sell":
            if free_btc < plan.planned_amount:
                return RiskDecision(False, "insufficient_btc_free_amount")
        if plan.min_amount and plan.planned_amount < plan.min_amount:
            return RiskDecision(False, "below_exchange_min_amount")
        if plan.max_amount is not None and plan.planned_amount > plan.max_amount:
            return RiskDecision(False, "above_exchange_max_amount")
        return RiskDecision(True, "ok")
