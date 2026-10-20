"""BUY funnel measurement. Logs pass/fail per gate; does not drop AND filters."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping

from bitbank_bot.amounts import plan_buy
from bitbank_bot.config import Config
from bitbank_bot.indicators import Trend, clause_score
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ONE, ZERO
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import MarketSnapshot, Position, Strategy


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    reason: str
    clauses: dict[str, bool] = field(default_factory=dict)


@dataclass
class BuyFunnelReport:
    gates: list[GateResult]
    setup_clauses: dict[str, dict[str, bool]]
    first_fail: str
    open: bool

    def gate(self, name: str) -> GateResult | None:
        for item in self.gates:
            if item.name == name:
                return item
        return None


def buy_setup_clauses(
    snap: MarketSnapshot,
    strategy: Strategy,
) -> dict[str, dict[str, bool]]:
    """Per-rule AND clauses. A rule fires only when every clause is true."""
    extend = strategy.cfg.buy3_extend
    buy3 = strategy.buy3
    buy4 = strategy.buy4
    extended_now = snap.close >= snap.ma * (ONE + extend)
    return {
        "BUY1": {
            "prev_ma_down": snap.prev_ma_trend == Trend.DOWN,
            "ma_flat_or_up": snap.ma_trend in {Trend.FLAT, Trend.UP},
            "crossed_up": snap.crossed_up,
        },
        "BUY2": {
            "ma_uptrend": snap.ma_trend == Trend.UP,
            "crossed_down": snap.crossed_down,
        },
        "BUY3": {
            "above_ma": snap.close > snap.ma or strategy._buy3,
            "extended_or_pullback": extended_now
            or buy3.phase in {"extended", "pullback"}
            or strategy._buy3,
            "pullback_complete": strategy._buy3 or buy3.phase == "pullback",
            "rising": snap.close > snap.prev_close or strategy._buy3,
        },
        "BUY4": {
            # Buy4Machine enters `dipped` on the first 5% dip, then fires only
            # on a later bar that rises. Same-bar dip+rise is not a setup.
            "ma_downtrend": snap.ma_trend == Trend.DOWN or strategy._buy4,
            "held_dip": buy4.phase == "dipped" or strategy._buy4,
            "bounce_after_dip": strategy._buy4,
        },
    }


def setup_fired(clauses: Mapping[str, Mapping[str, bool]]) -> tuple[bool, str]:
    for name, parts in clauses.items():
        if parts and all(parts.values()):
            return True, name
    return False, "no_buy_setup"


def measure_buy_funnel(
    *,
    snap: MarketSnapshot,
    strategy: Strategy,
    cfg: Config,
    risk: RiskManager,
    position: Position | None,
    pending: bool,
    htf_allow: bool,
    htf_reason: str,
    ws_stale: bool,
    executable: bool,
    available_jpy: Decimal,
    available_btc: Decimal,
    price: Decimal,
    ky_veto: bool,
    ky_reason: str,
    size_error: str | None = None,
) -> BuyFunnelReport:
    clauses = buy_setup_clauses(snap, strategy)
    setup_ok, setup_name = setup_fired(clauses)
    halt = risk.halt_reason()
    gates = [
        GateResult(
            "flat",
            position is None,
            "flat" if position is None else "in_position",
        ),
        GateResult(
            "pending",
            not pending,
            "no_pending" if not pending else "pending_order",
        ),
        GateResult(
            "setup",
            setup_ok,
            setup_name if setup_ok else "no_buy_setup",
            {f"{rule}.{key}": ok for rule, parts in clauses.items() for key, ok in parts.items()},
        ),
        GateResult(
            "htf",
            htf_allow,
            htf_reason,
        ),
        GateResult(
            "websocket",
            not ws_stale,
            "ws_ok" if not ws_stale else "stale_websocket",
        ),
        GateResult(
            "executable",
            executable,
            "executable" if executable else "heartbeat_or_not_executable",
        ),
        GateResult(
            "risk",
            halt is None,
            "ok" if halt is None else str(halt),
        ),
        GateResult(
            "size",
            False,
            "unevaluated",
        ),
        GateResult(
            "ky",
            not ky_veto,
            "ok" if not ky_veto else (ky_reason or "ky_veto"),
        ),
    ]
    if size_error:
        gates[7] = GateResult("size", False, size_error)
    else:
        plan = plan_buy(
            available_jpy=available_jpy,
            available_btc=available_btc,
            price=price,
            cfg=cfg,
            risk=risk,
        )
        gates[7] = GateResult("size", plan.ok, plan.reason)
    first_fail = ""
    for gate in gates:
        if not gate.passed:
            first_fail = gate.reason or gate.name
            break
    return BuyFunnelReport(
        gates=gates,
        setup_clauses={name: dict(parts) for name, parts in clauses.items()},
        first_fail=first_fail,
        open=all(gate.passed for gate in gates),
    )


def log_buy_funnel(report: BuyFunnelReport) -> None:
    for gate in report.gates:
        payload: dict[str, object] = {
            "gate": gate.name,
            "passed": gate.passed,
            "reason": gate.reason,
        }
        if gate.clauses:
            payload["clauses"] = gate.clauses
            payload["clause_score"] = str(clause_score(gate.clauses))
        slog("BUY_GATE", "pass" if gate.passed else "fail", **payload)
    slog(
        "BUY_CHECK",
        "funnel_open" if report.open else "funnel_blocked",
        open=report.open,
        first_fail=report.first_fail or "none",
        setup_scores={
            name: str(clause_score(parts)) for name, parts in report.setup_clauses.items()
        },
    )


def paper_balances(
    cfg: Config,
    paper_jpy: Decimal,
    paper_btc: Decimal,
    position: Position | None,
) -> tuple[Decimal, Decimal]:
    """No-key path only. Matches Engine._balances when keys are absent."""
    jpy = cfg.dry_run_free_jpy
    btc = cfg.dry_run_free_btc
    if paper_jpy > ZERO or paper_btc > ZERO or position is not None:
        jpy = paper_jpy
        btc = paper_btc
    if position is not None:
        btc = max(btc, position.amount)
    return D(jpy), D(btc)
