#!/usr/bin/env python3
"""Full-tree syntax / import / obvious bug scan (chan-pro style exhaustive finder)."""

from __future__ import annotations

import ast
import json
import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TARGETS = [SRC, ROOT / "tests", ROOT / "scripts", ROOT / "run.py", ROOT / "main.py", ROOT / "diagnostics.py"]


def iter_py_files() -> list[Path]:
    files: list[Path] = []
    for target in TARGETS:
        if target.is_file() and target.suffix == ".py":
            files.append(target)
            continue
        if not target.is_dir():
            continue
        files.extend(sorted(target.rglob("*.py")))
    return files


def audit_file(path: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    rel = str(path.relative_to(ROOT))
    try:
        source = path.read_text(encoding="utf-8")
    except Exception as exc:
        return [{"file": rel, "kind": "read_error", "detail": type(exc).__name__}]
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError as exc:
        return [
            {
                "file": rel,
                "kind": "syntax_error",
                "line": exc.lineno,
                "detail": exc.msg,
            }
        ]
    try:
        py_compile.compile(str(path), doraise=True)
    except py_compile.PyCompileError as exc:
        findings.append({"file": rel, "kind": "compile_error", "detail": str(exc)})
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            findings.append(
                {
                    "file": rel,
                    "kind": "bare_except",
                    "line": getattr(node, "lineno", None),
                    "detail": "bare except",
                }
            )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"eval", "exec"}:
                findings.append(
                    {
                        "file": rel,
                        "kind": "dangerous_call",
                        "line": getattr(node, "lineno", None),
                        "detail": node.func.id,
                    }
                )
    return findings


def main() -> int:
    all_findings: list[dict[str, object]] = []
    files = iter_py_files()
    for path in files:
        all_findings.extend(audit_file(path))
    report = {
        "files_scanned": len(files),
        "findings": all_findings,
        "ok": not any(f["kind"] in {"syntax_error", "compile_error"} for f in all_findings),
    }
    out = ROOT / "reports" / "ast_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"files_scanned": report["files_scanned"], "findings": len(all_findings), "ok": report["ok"]}))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())