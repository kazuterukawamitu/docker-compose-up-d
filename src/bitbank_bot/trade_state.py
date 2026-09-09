"""Explicit trade phases. Does not replace README BUY/SELL rules."""

from __future__ import annotations

from enum import Enum

from bitbank_bot.logging_setup import slog


class TradePhase(str, Enum):
    WAIT = "WAIT"
    SIGNAL_FOUND = "SIGNAL_FOUND"
    ORDERING = "ORDERING"
    PENDING = "PENDING"
    POSITION = "POSITION"
    FLAT = "FLAT"


class TradeStateMachine:
    def __init__(self, phase: TradePhase = TradePhase.WAIT) -> None:
        self.phase = phase

    def transition(self, nxt: TradePhase, *, reason: str = "") -> TradePhase:
        if nxt is self.phase:
            return self.phase
        slog(
            "TRADE_STATE",
            f"{self.phase.value}->{nxt.value}",
            from_phase=self.phase.value,
            to_phase=nxt.value,
            reason=reason,
        )
        self.phase = nxt
        return self.phase

    def from_bot(self, *, pending: bool, in_position: bool, side: str | None) -> TradePhase:
        if pending:
            return self.transition(TradePhase.PENDING, reason="pending_order")
        if in_position:
            return self.transition(TradePhase.POSITION, reason="open_position")
        if side in {"buy", "sell"}:
            return self.transition(TradePhase.SIGNAL_FOUND, reason=side or "")
        if self.phase is TradePhase.POSITION:
            return self.transition(TradePhase.FLAT, reason="flat")
        return self.transition(TradePhase.WAIT, reason="no_setup")
