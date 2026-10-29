#!/usr/bin/env python3
"""Docker-comparable gap agent: purpose vs current code.

Scans the production package for the six known execution gaps and prints a
pass/fail report. Read-only. Never places an order.

    python3 scripts/gap_agent.py
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "bitbank_bot"


def _read(name: str) -> str:
    return (SRC / name).read_text(encoding="utf-8")


def _has(haystack: str, *needles: str) -> bool:
    return all(n in haystack for n in needles)


CHECKS: list[tuple[str, str, Callable[[], tuple[bool, str]]]] = []


def check(name: str, purpose: str):
    def deco(fn):
        CHECKS.append((name, purpose, fn))
        return fn

    return deco


@check("SELL_INTRABAR", "Ticker/protective exits must not wait for the next closed 1h bar")
def c_sell_intrabar() -> tuple[bool, str]:
    engine = _read("engine.py")
    decision = _read("decision.py")
    ok = _has(decision, "def price_exit") and _has(engine, "_protective_signal", "price_exit")
    return ok, "price_exit + Engine._protective_signal" if ok else "missing ticker exit path"


@check("STOP_MARKET", "Independent stop / emergency flatten path must exist")
def c_stop() -> tuple[bool, str]:
    decision = _read("decision.py")
    orders = _read("orders.py")
    ok = _has(decision, '"STOP"', "stop_loss_pct") and (
        "order_type" in orders or "market" in orders
    )
    return ok, "STOP signal + market replace" if ok else "no STOP path"


@check("CANCEL_PENDING", "Canceled orders must clear state.pending")
def c_cancel() -> tuple[bool, str]:
    orders = _read("orders.py")
    engine = _read("engine.py")
    ok = _has(orders, "CANCELED", "canceled") and _has(
        engine, 'result.reason == "canceled"', "pending cleared"
    )
    return ok, "canceled → clear pending" if ok else "cancel leaves pending"


@check("PARTIAL_NOTIONAL", "Incremental fills must use delta notional, not cum avg × delta")
def c_partial() -> tuple[bool, str]:
    engine = _read("engine.py")
    ok = _has(engine, "incremental_notional", "filled_notional")
    bad = "delta * avg" in engine and "incremental_notional" not in engine
    return ok and not bad, "incremental_notional used" if ok else "cum-avg × delta risk"


@check("FEE_PNL", "Realized PnL must deduct quote fees")
def c_fee() -> tuple[bool, str]:
    engine = _read("engine.py")
    orders = _read("orders.py")
    ok = _has(engine, "fee_jpy", "taker_fee_rate") and _has(orders, "fee_jpy")
    return ok, "fee_jpy on fills + PnL" if ok else "fee-blind PnL"


@check("RECONCILE", "Live startup must reconcile assets and active orders")
def c_reconcile() -> tuple[bool, str]:
    engine = _read("engine.py")
    ok = _has(engine, "def reconcile", "get_active_orders", "free_amount")
    return ok, "Engine.reconcile" if ok else "local state only"


@check("ENTROPY_PNL", "Shannon entropy + daily PnL must feed decisions")
def c_entropy() -> tuple[bool, str]:
    decision = _read("decision.py")
    engine = _read("engine.py")
    ok = _has(decision, "shannon_entropy", "daily_pnl") and _has(
        engine, "shannon_entropy", "daily_pnl"
    )
    return ok, "entropy + daily_pnl wired" if ok else "missing entropy/PnL signals"


@check("SYNTAX", "All package modules must parse")
def c_syntax() -> tuple[bool, str]:
    bad: list[str] = []
    for path in sorted(SRC.glob("*.py")):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            bad.append(f"{path.name}:{exc.lineno}")
    return not bad, "ok" if not bad else ", ".join(bad)


def main() -> int:
    print("gap_agent  purpose vs package")
    print("=" * 72)
    failed = 0
    for name, purpose, fn in CHECKS:
        ok, detail = fn()
        mark = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"[{mark}] {name}")
        print(f"       {purpose}")
        print(f"       {detail}")
    print("=" * 72)
    print(f"result: {'ALL PASS' if failed == 0 else f'{failed} FAIL'}")
    docker = ROOT / "Dockerfile"
    compose = ROOT / "docker-compose.yml"
    print(f"docker: {'yes' if docker.exists() else 'no'}  compose: {'yes' if compose.exists() else 'no'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
