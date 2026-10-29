#!/usr/bin/env python3
"""Python ↔ JSON purpose index for instant search across the bot package.

Builds `data/purpose_index.json` mapping module → purpose keywords so agents
and operators can locate the path for a goal in one lookup.

    python3 scripts/purpose_index.py
    python3 scripts/purpose_index.py --search SELL
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "bitbank_bot"
OUT = ROOT / "data" / "purpose_index.json"

# Pareto: critical execution path first (80/20 of live risk).
PURPOSE_HINTS: dict[str, list[str]] = {
    "engine.py": [
        "loop",
        "reconcile",
        "protective_exit",
        "pending",
        "daily_pnl",
        "execution",
    ],
    "orders.py": ["create_order", "cancel", "fee", "partial_fill", "incremental_notional"],
    "decision.py": ["shannon_entropy", "price_exit", "stop", "take_profit", "fee_edge"],
    "strategy.py": ["granville", "BUY1", "SELL1", "moving_average"],
    "risk.py": ["kill_switch", "daily_loss", "circuit_breaker"],
    "quantum_engine.py": [
        "probability_state_updater",
        "gravity_well_escape",
        "multi_scenario",
        "self_healing",
        "annealing",
    ],
    "rest_client.py": ["bitbank", "connection", "hmac", "live"],
    "amounts.py": ["sizing", "TARGET", "PLANNED", "ACTUAL"],
    "sentry_setup.py": ["sentry", "observability", "error_reporting"],
    "screen.py": ["iterm", "取引画面", "datetime_pnl"],
}


def index_module(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    doc = ast.get_docstring(ast.parse(text, filename=str(path))) or ""
    defs = [
        node.name
        for node in ast.walk(ast.parse(text, filename=str(path)))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    hints = PURPOSE_HINTS.get(path.name, [])
    return {
        "module": path.name,
        "path": str(path.relative_to(ROOT)),
        "doc_head": " ".join(doc.split())[:240],
        "symbols": sorted(set(defs))[:80],
        "purpose_hints": hints,
    }


def build() -> dict[str, object]:
    modules = [index_module(p) for p in sorted(SRC.glob("*.py"))]
    return {
        "purpose": (
            "possibility_success, connection_success, operation_success, "
            "execution_success, performance_success for Bitbank btc_jpy"
        ),
        "patches": [
            "intrabar_stop_tp",
            "cancel_clears_pending",
            "incremental_partial_notional",
            "fee_aware_pnl",
            "startup_reconcile",
        ],
        "modules": modules,
    }


def search(payload: dict[str, object], needle: str) -> list[dict[str, object]]:
    q = needle.lower()
    hits: list[dict[str, object]] = []
    for mod in payload.get("modules", []):
        blob = json.dumps(mod, ensure_ascii=False).lower()
        if q in blob:
            hits.append(
                {
                    "module": mod["module"],
                    "path": mod["path"],
                    "purpose_hints": mod.get("purpose_hints") or [],
                }
            )
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Build/search purpose index JSON")
    parser.add_argument("--search", default="", help="keyword to find instantly")
    args = parser.parse_args()
    payload = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT} modules={len(payload['modules'])}")
    if args.search:
        hits = search(payload, args.search)
        print(json.dumps(hits, indent=2, ensure_ascii=False))
        return 0 if hits else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
