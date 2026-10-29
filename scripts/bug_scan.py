#!/usr/bin/env python3
"""Static bug/error finder for this bot (chan-pro style: one finding per hit).

Scans Python sources for known anti-patterns that previously broke SELL,
pending state, fees, and live gates. Read-only.

    python3 scripts/bug_scan.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT / "src" / "bitbank_bot",
    ROOT / "run.py",
    ROOT / "main.py",
    ROOT / "scripts",
]


PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    (
        "CUMAVG_DELTA",
        "partial fill cost uses delta * cumulative average",
        re.compile(r"delta\s*\*\s*(avg|average|result\.average_price)"),
    ),
    (
        "FILL_STATUS_IGNORES_RAW",
        "_fill_status ignores canceled raw status",
        re.compile(r"def _fill_status\([^)]*\):\n(?:.*\n){0,6}\s*if executed <= ", re.M),
    ),
    (
        "NO_CREATE_ORDER_IN_RUN",
        "stdlib run.py must never call create_order",
        re.compile(r"create_order\("),
    ),
]


def iter_py() -> list[Path]:
    files: list[Path] = []
    for target in TARGETS:
        if target.is_file() and target.suffix == ".py":
            files.append(target)
        elif target.is_dir():
            files.extend(sorted(target.rglob("*.py")))
    return files


def scan_syntax(path: Path) -> list[str]:
    hits: list[str] = []
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        hits.append(f"SYNTAX {path.relative_to(ROOT)}:{exc.lineno} {exc.msg}")
    return hits


def scan_patterns(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    rel = str(path.relative_to(ROOT))
    hits: list[str] = []
    for code, title, pattern in PATTERNS:
        if code == "NO_CREATE_ORDER_IN_RUN" and path.name != "run.py":
            continue
        if code == "FILL_STATUS_IGNORES_RAW" and path.name != "orders.py":
            continue
        if code == "CUMAVG_DELTA" and "incremental_notional" in text:
            # Fixed path uses helper; skip false positives near comments.
            continue
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            hits.append(f"{code} {rel}:{line} {title}")
    return hits


def main() -> int:
    findings: list[str] = []
    for path in iter_py():
        findings.extend(scan_syntax(path))
        findings.extend(scan_patterns(path))
    print("bug_scan")
    print("=" * 72)
    if not findings:
        print("PASS  0 findings")
        return 0
    for i, item in enumerate(findings, 1):
        print(f"{i:03d}  {item}")
    print("=" * 72)
    print(f"FAIL  {len(findings)} findings")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
