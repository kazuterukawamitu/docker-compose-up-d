#!/usr/bin/env python3
"""AST inventory of the Bitbank bot. Writes reports/ast_report.json and reports/dependency_graph.json."""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
OUT = ROOT / "reports"


def analyze() -> dict:
    py_files = sorted(SRC.rglob("*.py"))
    modules: dict[str, dict] = {}
    graph: dict[str, list[str]] = {}
    for path in py_files:
        rel = str(path.relative_to(ROOT))
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        imports: list[str] = []
        classes: list[str] = []
        functions: list[str] = []
        calls: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                imports.append(mod)
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
        local = sorted({imp for imp in imports if imp.startswith("bitbank_bot")})
        modules[rel] = {
            "imports": sorted(set(imports)),
            "local_imports": local,
            "classes": classes,
            "functions": functions,
            "calls": sorted(set(calls)),
        }
        graph[rel] = local
    return {"modules": modules, "dependency_graph": graph}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    payload = analyze()
    (OUT / "ast_report.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (OUT / "dependency_graph.json").write_text(
        json.dumps(payload["dependency_graph"], indent=2), encoding="utf-8"
    )
    print(f"wrote {OUT / 'ast_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
