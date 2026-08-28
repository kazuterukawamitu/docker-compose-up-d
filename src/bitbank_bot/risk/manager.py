from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import time

from bitbank_bot.config import Settings
from bitbank_bot.exceptions import RiskBlocked
from bitbank_bot.models import Signal, Snapshot


@dataclass
class RiskDecision:
    allowed: bool
    reason: str


class RiskManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.consecutive_failures = 0
        self.pause_until_ms = 0
        self.halted = False
        self.halt_reason = ""

    def kill_file(self) -> Path:
        return self.settings.state_dir / "KILL"

    def check(self, signal: Signal, snapshot: Snapshot, daily_pnl: Decimal, total_pnl: Decimal) -> RiskDecision:
        if self.halted:
            return RiskDecision(False, f"halted: {self.halt_reason}")
        if self.settings.kill_switch or self.kill_file().exists():
            return RiskDecision(False, "kill switch is set")
        now = snapshot.now_ms or int(time.time() * 1000)
        if now < self.pause_until_ms:
            return RiskDecision(False, "circuit breaker pause after exchange errors")
        age = now - snapshot.ticker.timestamp_ms
        if age > self.settings.stale_ms:
            return RiskDecision(False, f"stale market data age_ms={age}")
        if snapshot.circuit_mode not in {"NONE", ""} and signal.action != "HOLD":
            if self.settings.order_type == "market":
                return RiskDecision(False, f"market orders blocked during circuit_break mode={snapshot.circuit_mode}")
        if daily_pnl <= -self.settings.max_daily_loss_jpy:
            return RiskDecision(False, "max daily loss reached")
        if total_pnl <= -self.settings.max_loss_jpy:
            return RiskDecision(False, "max total loss reached")
        if signal.action == "BUY":
            if snapshot.position.amount >= self.settings.max_position_btc:
                return RiskDecision(False, "max position already open")
            if snapshot.jpy_free <= 0:
                return RiskDecision(False, "insufficient JPY")
        if signal.action == "SELL":
            if snapshot.position.amount <= 0 and snapshot.btc_free <= 0:
                return RiskDecision(False, "no BTC to sell")
        return RiskDecision(True, "ok")

    def require(self, signal: Signal, snapshot: Snapshot, daily_pnl: Decimal, total_pnl: Decimal) -> None:
        decision = self.check(signal, snapshot, daily_pnl, total_pnl)
        if not decision.allowed:
            raise RiskBlocked(decision.reason)

    def record_success(self) -> None:
        self.consecutive_failures = 0

    def record_failure(self, error: Exception) -> None:
        self.consecutive_failures += 1
        backoff_ms = min(300_000, 5_000 * (2 ** min(self.consecutive_failures, 6)))
        self.pause_until_ms = int(time.time() * 1000) + backoff_ms
        if self.consecutive_failures >= 8:
            self.halted = True
            self.halt_reason = f"too many consecutive failures: {error}"
