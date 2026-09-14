#!/usr/bin/env python3
"""AST map of src/bitbank_bot. Writes reports/*.json. Never prints secrets."""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
OUT = ROOT / "reports"


def _walk() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def analyze() -> dict:
    files: dict[str, dict] = {}
    graph: dict[str, list[str]] = {}
    markers = (
        "DRY_RUN",
        "LIVE_TRADING",
        "SIGNAL_ONLY",
        "synthetic_fallback",
        "create_order",
        "HOLD",
        "BUY",
        "SELL",
        "bitFlyer",
        "coincheck",
        "gmo",
    )
    for path in _walk():
        rel = str(path.relative_to(ROOT))
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        imports: list[str] = []
        classes: list[str] = []
        functions: list[str] = []
        calls: list[str] = []
        hits: dict[str, int] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                functions.append(node.name)
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute):
                    calls.append(func.attr)
                elif isinstance(func, ast.Name):
                    calls.append(func.id)
        text = path.read_text(encoding="utf-8")
        for mark in markers:
            count = text.count(mark)
            if count:
                hits[mark] = count
        files[rel] = {
            "imports": sorted(set(imports)),
            "classes": classes,
            "functions": functions,
            "create_order_calls": calls.count("create_order"),
            "markers": hits,
        }
        local = [
            name
            for name in imports
            if name and name.startswith("bitbank_bot")
        ]
        graph[rel] = sorted(set(local))
    return {"files": files, "graph": graph}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    data = analyze()
    (OUT / "ast_report.json").write_text(
        json.dumps(data["files"], indent=2), encoding="utf-8"
    )
    (OUT / "dependency_graph.json").write_text(
        json.dumps(data["graph"], indent=2), encoding="utf-8"
    )
    print(f"wrote {OUT / 'ast_report.json'} files={len(data['files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
