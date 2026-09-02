"""Kill switch, max position, and daily loss caps.

Operator kill (KILL_SWITCH=true or data/KILL) is distinct from a daily PnL
halt. Daily halt must not latch as kill_switch or survive into the next JST day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO

JST = timezone(timedelta(hours=9))


def jst_today() -> date:
    return datetime.now(JST).date()


def jst_date_from_ms(timestamp_ms: int) -> date:
    return datetime.fromtimestamp(timestamp_ms / 1000.0, tz=JST).date()


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
        self.daily_pnl_floor = cfg.daily_pnl_floor
        self.daily_pnl = D(daily_pnl)
        self.daily_pnl_date = daily_pnl_date or jst_today().isoformat()
        self._operator_killed = cfg.kill_switch if killed is None else bool(killed)
        self._as_of: date | None = None
        self._consecutive_errors = 0
        self._auth_failed = False
        self._peak_equity = ZERO
        self._equity = ZERO

    def set_as_of(self, timestamp_ms: int) -> None:
        self._as_of = jst_date_from_ms(int(timestamp_ms))
        self._roll_day()

    def _today(self) -> date:
        return self._as_of if self._as_of is not None else jst_today()

    def _roll_day(self) -> None:
        today = self._today().isoformat()
        if today != self.daily_pnl_date:
            self.daily_pnl = ZERO
            self.daily_pnl_date = today

    def _daily_halt_reason(self) -> str | None:
        if self.daily_pnl_floor > ZERO and self.daily_pnl <= -self.daily_pnl_floor:
            return "daily_pnl_floor"
        if self.max_daily_loss_jpy > ZERO and self.daily_pnl <= -self.max_daily_loss_jpy:
            return "max_daily_loss"
        return None

    @property
    def operator_killed(self) -> bool:
        return bool(self._operator_killed or self.cfg.kill_switch)

    def halt_reason(self) -> str | None:
        self._roll_day()
        if self._auth_failed:
            return "auth_failure"
        limit = int(self.cfg.circuit_breaker_errors or 0)
        if limit > 0 and self._consecutive_errors >= limit:
            return "circuit_breaker"
        if self.operator_killed:
            return "kill_switch"
        if Path(self.cfg.kill_switch_path).exists():
            return "kill_switch"
        max_dd = D(self.cfg.max_drawdown_jpy or 0)
        if max_dd > ZERO and self._peak_equity > ZERO:
            drawdown = self._peak_equity - self._equity
            if drawdown >= max_dd:
                return "max_drawdown"
        return self._daily_halt_reason()

    @property
    def killed(self) -> bool:
        return self.halt_reason() is not None

    def note_auth_failure(self) -> None:
        self._auth_failed = True
        slog("RISK", "auth failure; no further orders until restart")

    def note_api_error(self) -> None:
        self._consecutive_errors += 1
        slog("RISK", "api error streak", count=self._consecutive_errors)

    def note_api_ok(self) -> None:
        self._consecutive_errors = 0

    def update_equity(self, jpy: Decimal, btc: Decimal, price: Decimal) -> None:
        equity = D(jpy) + D(btc) * D(price)
        self._equity = equity
        if equity > self._peak_equity:
            self._peak_equity = equity

    def record_realized_pnl(self, pnl_jpy: Decimal) -> None:
        self._roll_day()
        self.daily_pnl += D(pnl_jpy)
        slog("RISK", "realized pnl", pnl=str(pnl_jpy), daily_pnl=str(self.daily_pnl))
        reason = self._daily_halt_reason()
        if reason:
            slog("RISK", "daily halt armed", reason=reason, daily_pnl=str(self.daily_pnl))

    def check_stale(self, age_sec: float) -> RiskDecision:
        limit = float(self.cfg.stale_ws_sec)
        if age_sec > limit:
            return RiskDecision(False, ZERO, "stale_data", False)
        return RiskDecision(True, ZERO, "ok", False)

    def check_buy(self, current_btc: Decimal, requested_btc: Decimal) -> RiskDecision:
        reason = self.halt_reason()
        if reason:
            return RiskDecision(False, ZERO, reason, True)
        headroom = self.max_position_btc - D(current_btc)
        if headroom <= ZERO:
            return RiskDecision(False, ZERO, "max_position", False)
        capped = min(D(requested_btc), headroom, self.max_order_btc)
        if capped <= ZERO:
            return RiskDecision(False, ZERO, "capped_to_zero", False)
        return RiskDecision(True, capped, "ok", False)

    def check_sell(self, requested_btc: Decimal) -> RiskDecision:
        if self._auth_failed:
            return RiskDecision(False, ZERO, "auth_failure", True)
        limit = int(self.cfg.circuit_breaker_errors or 0)
        if limit > 0 and self._consecutive_errors >= limit:
            return RiskDecision(False, ZERO, "circuit_breaker", True)
        if self.cfg.kill_switch or self._operator_killed:
            return RiskDecision(False, ZERO, "kill_switch", True)
        capped = min(D(requested_btc), self.max_order_btc)
        return RiskDecision(True, capped, "ok", self.killed)
