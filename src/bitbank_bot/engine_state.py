"""Persisted bot state. JSON only; there is no database."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from bitbank_bot.config import Config
from bitbank_bot.money import D, ZERO
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import Position


@dataclass
class PendingOrder:
    order_id: str
    side: str
    kind: str
    tp_pct: Decimal | None
    index: int
    timestamp_ms: int
    amount: Decimal
    filled_amount: Decimal = ZERO


@dataclass
class BotState:
    position: Position | None
    risk: RiskManager
    last_candle_ts: int
    started_at: float
    pending: PendingOrder | None = None
    paper_jpy: Decimal = ZERO
    paper_btc: Decimal = ZERO


def load_state(path: str | Path, cfg: Config) -> BotState:
    risk = RiskManager(cfg)
    position = None
    last_ts = 0
    pending: PendingOrder | None = None
    paper_jpy = cfg.dry_run_free_jpy
    paper_btc = cfg.dry_run_free_btc
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
        pending_raw = raw.get("pending")
        if pending_raw and pending_raw.get("order_id"):
            tp_raw = pending_raw.get("tp_pct")
            pending = PendingOrder(
                order_id=str(pending_raw["order_id"]),
                side=str(pending_raw.get("side") or ""),
                kind=str(pending_raw.get("kind") or ""),
                tp_pct=D(tp_raw) if tp_raw not in (None, "") else None,
                index=int(pending_raw.get("index") or 0),
                timestamp_ms=int(pending_raw.get("timestamp_ms") or 0),
                amount=D(pending_raw.get("amount") or 0),
                filled_amount=D(pending_raw.get("filled_amount") or 0),
            )
        if raw.get("paper_jpy") not in (None, ""):
            paper_jpy = D(raw.get("paper_jpy"))
        if raw.get("paper_btc") not in (None, ""):
            paper_btc = D(raw.get("paper_btc"))
    return BotState(
        position, risk, last_ts, time.monotonic(), pending, paper_jpy, paper_btc
    )


def save_state(path: str | Path, state: BotState) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "daily_pnl": str(state.risk.daily_pnl),
        "daily_pnl_date": state.risk.daily_pnl_date,
        "operator_killed": state.risk.operator_killed,
        "last_candle_ts": state.last_candle_ts,
        "paper_jpy": str(state.paper_jpy),
        "paper_btc": str(state.paper_btc),
        "position": None,
        "pending": None,
    }
    if state.pending:
        payload["pending"] = {
            "order_id": state.pending.order_id,
            "side": state.pending.side,
            "kind": state.pending.kind,
            "tp_pct": str(state.pending.tp_pct) if state.pending.tp_pct is not None else "",
            "index": state.pending.index,
            "timestamp_ms": state.pending.timestamp_ms,
            "amount": str(state.pending.amount),
            "filled_amount": str(state.pending.filled_amount),
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
