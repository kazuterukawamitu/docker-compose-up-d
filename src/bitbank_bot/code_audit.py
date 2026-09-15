"""Static analysis of this repo. Does not trade and does not load .env secrets.

Used by ``scripts/analyze_ast.py``, ``scripts/dump_all_source.py``, and
``scripts/completion_percent.py``. Output JSON/markdown is for review; the
concatenated dump is not an executable program.
"""

from __future__ import annotations

import ast
import json
import py_compile
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "htmlcov",
        "node_modules",
        "dist",
        "build",
    }
)
SECRET_FILE_NAMES = frozenset({".env", ".env.local", ".env.production"})
OTHER_EXCHANGE_RE = re.compile(
    r"\b(bitflyer|coincheck|zaif|binance|bybit|kraken|gmo.?coin|bitfinex)\b",
    re.IGNORECASE,
)
PAIR_ALIAS_RE = re.compile(
    r"\b(btc_jpn|jpn_btc|jpy_btc|jpc_btc|btc_jpc|btcjpy|jpn_jpy|jpc_jpy)\b",
    re.IGNORECASE,
)
BUY_SELL_HOLD_RE = re.compile(r"\b(BUY[1-4]|SELL[1-4]|HOLD|no_buy_setup)\b")
SRC_CREATE_ORDER_ALLOWED = frozenset(
    {
        "src/bitbank_bot/orders.py",
        "src/bitbank_bot/api_client.py",
    }
)
FILE_ROLES: dict[str, dict[str, Any]] = {
    "src/bitbank_bot/__init__.py": {
        "role": "package",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "src/bitbank_bot/__main__.py": {
        "role": "entrypoint",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "src/bitbank_bot/api_client.py": {
        "role": "api_facade",
        "in_use": True,
        "api": True,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "src/bitbank_bot/rest_client.py": {
        "role": "api_rest",
        "in_use": True,
        "api": True,
        "order": True,
        "strategy": False,
        "config": False,
    },
    "src/bitbank_bot/websocket_client.py": {
        "role": "api_ws",
        "in_use": True,
        "api": True,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "src/bitbank_bot/market_data.py": {
        "role": "market_data",
        "in_use": True,
        "api": True,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "src/bitbank_bot/strategy.py": {
        "role": "strategy",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": True,
        "config": False,
    },
    "src/bitbank_bot/rate_engine.py": {
        "role": "rates",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "src/bitbank_bot/execution_gate.py": {
        "role": "execution_gate",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "src/bitbank_bot/trade_signal_executor.py": {
        "role": "order_path",
        "in_use": True,
        "api": False,
        "order": True,
        "strategy": False,
        "config": False,
    },
    "src/bitbank_bot/orders.py": {
        "role": "order_executor",
        "in_use": True,
        "api": False,
        "order": True,
        "strategy": False,
        "config": False,
    },
    "src/bitbank_bot/engine.py": {
        "role": "loop",
        "in_use": True,
        "api": False,
        "order": True,
        "strategy": True,
        "config": False,
    },
    "src/bitbank_bot/main.py": {
        "role": "cli",
        "in_use": True,
        "api": True,
        "order": False,
        "strategy": False,
        "config": True,
    },
    "src/bitbank_bot/launch.py": {
        "role": "launcher",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": True,
    },
    "src/bitbank_bot/config.py": {
        "role": "config",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": True,
    },
    "src/bitbank_bot/risk.py": {
        "role": "risk",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "src/bitbank_bot/amounts.py": {
        "role": "sizer",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "src/bitbank_bot/reconciliation.py": {
        "role": "reconcile",
        "in_use": True,
        "api": True,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "src/bitbank_bot/screen.py": {
        "role": "trading_screen",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "src/bitbank_bot/watchdog.py": {
        "role": "watchdog",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "src/bitbank_bot/logging_setup.py": {
        "role": "logging",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "src/bitbank_bot/money.py": {
        "role": "money",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "src/bitbank_bot/indicators.py": {
        "role": "indicators",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": True,
        "config": False,
    },
    "src/bitbank_bot/multi_timeframe.py": {
        "role": "htf_filter",
        "in_use": True,
        "api": True,
        "order": False,
        "strategy": True,
        "config": False,
    },
    "src/bitbank_bot/preflight.py": {
        "role": "preflight",
        "in_use": True,
        "api": True,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "src/bitbank_bot/instance_lock.py": {
        "role": "lock",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "src/bitbank_bot/backtest.py": {
        "role": "backtest",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": True,
        "config": False,
    },
    "src/bitbank_bot/code_audit.py": {
        "role": "analysis",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "src/bitbank_bot/pytest_plugin.py": {
        "role": "test_plugin",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "run.py": {
        "role": "stdlib_screen_fallback",
        "in_use": True,
        "api": True,
        "order": False,
        "strategy": True,
        "config": False,
    },
    "main.py": {
        "role": "root_cli",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "diagnostics.py": {
        "role": "diagnostics",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": True,
    },
    "start.sh": {
        "role": "launcher",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": True,
    },
    "scripts/analyze_ast.py": {
        "role": "analysis",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "scripts/dump_all_source.py": {
        "role": "analysis",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "scripts/completion_percent.py": {
        "role": "analysis",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "scripts/bitbank_execution_audit.py": {
        "role": "audit",
        "in_use": True,
        "api": True,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "scripts/home_start.sh": {
        "role": "launcher_helper",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "scripts/install_launch_alias.sh": {
        "role": "launcher_helper",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "scripts/run_bot.sh": {
        "role": "launcher_helper",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": False,
    },
    "scripts/run_tests.sh": {
        "role": "test_helper",
        "in_use": True,
        "api": False,
        "order": False,
        "strategy": False,
        "config": False,
    },
}


@dataclass
class FileAst:
    path: str
    imports: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    create_order_defs: list[dict[str, Any]] = field(default_factory=list)
    create_order_calls: list[dict[str, Any]] = field(default_factory=list)
    buy_sell_hold: list[dict[str, Any]] = field(default_factory=list)
    pair_aliases: list[dict[str, Any]] = field(default_factory=list)
    other_exchanges: list[dict[str, Any]] = field(default_factory=list)
    bare_excepts: list[dict[str, Any]] = field(default_factory=list)
    parse_error: str = ""


def rel(root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def is_secret_path(path: Path) -> bool:
    name = path.name
    if name in SECRET_FILE_NAMES:
        return True
    if name.startswith(".env") and name != ".env.example":
        return True
    if name.endswith((".pem", ".key")):
        return True
    return False


def iter_files(root: Path, suffixes: tuple[str, ...] = (".py",)) -> list[Path]:
    out: list[Path] = []
    root = root.resolve()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if is_secret_path(path):
            continue
        if path.suffix in suffixes or path.name in {"start.sh"}:
            out.append(path)
    return sorted(out)


def _attr_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _attr_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _parse_file(root: Path, path: Path) -> FileAst:
    rel_path = rel(root, path)
    info = FileAst(path=rel_path)
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        info.parse_error = type(exc).__name__
        return info
    try:
        tree = ast.parse(source, filename=rel_path)
    except SyntaxError as exc:
        info.parse_error = f"SyntaxError:{exc.lineno}"
        return info

    func_stack: list[str] = []
    class_stack: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                info.imports.append(alias.name)
            self.generic_visit(node)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            mod = node.module or ""
            info.imports.append(mod)
            self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            class_stack.append(node.name)
            info.classes.append(".".join(class_stack))
            self.generic_visit(node)
            class_stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            func_stack.append(node.name)
            qual = ".".join([*class_stack, *func_stack])
            info.functions.append(qual)
            if node.name == "create_order":
                info.create_order_defs.append(
                    {"file": rel_path, "lineno": node.lineno, "qual": qual}
                )
            self.generic_visit(node)
            func_stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.visit_FunctionDef(node)  # type: ignore[arg-type]

        def visit_Call(self, node: ast.Call) -> None:
            name = _attr_name(node.func)
            if name.endswith("create_order") or name == "create_order":
                info.create_order_calls.append(
                    {
                        "file": rel_path,
                        "lineno": node.lineno,
                        "qual": ".".join([*class_stack, *func_stack]),
                        "name": name,
                    }
                )
            self.generic_visit(node)

        def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
            if node.type is None:
                info.bare_excepts.append(
                    {
                        "file": rel_path,
                        "lineno": node.lineno,
                        "qual": ".".join([*class_stack, *func_stack]),
                    }
                )
            self.generic_visit(node)

        def visit_Constant(self, node: ast.Constant) -> None:
            if isinstance(node.value, str):
                text = node.value
                if BUY_SELL_HOLD_RE.search(text):
                    info.buy_sell_hold.append(
                        {"file": rel_path, "lineno": node.lineno, "text": text[:80]}
                    )
                for match in PAIR_ALIAS_RE.finditer(text):
                    info.pair_aliases.append(
                        {
                            "file": rel_path,
                            "lineno": node.lineno,
                            "text": match.group(0),
                        }
                    )
                for match in OTHER_EXCHANGE_RE.finditer(text):
                    info.other_exchanges.append(
                        {
                            "file": rel_path,
                            "lineno": node.lineno,
                            "text": match.group(0),
                        }
                    )
            self.generic_visit(node)

    Visitor().visit(tree)
    info.imports = sorted(set(info.imports))
    return info


def analyze_python(root: Path) -> dict[str, Any]:
    files = [p for p in iter_files(root, (".py",)) if p.suffix == ".py"]
    parsed = [_parse_file(root, path) for path in files]
    modules: dict[str, dict[str, Any]] = {}
    imported_by: dict[str, list[str]] = {}
    for item in parsed:
        modules[item.path] = {
            "imports": item.imports,
            "classes": item.classes,
            "functions": item.functions,
            "parse_error": item.parse_error,
        }
        for imp in item.imports:
            imported_by.setdefault(imp, []).append(item.path)
    create_order_calls = [row for item in parsed for row in item.create_order_calls]
    src_calls = [
        row
        for row in create_order_calls
        if row["file"].startswith("src/bitbank_bot/")
    ]
    unexpected_src_calls = [
        row for row in src_calls if row["file"] not in SRC_CREATE_ORDER_ALLOWED
    ]
    other_src = [
        row
        for item in parsed
        for row in item.other_exchanges
        if item.path.startswith("src/")
        and item.path != "src/bitbank_bot/code_audit.py"
    ]
    return {
        "root": str(root),
        "file_count": len(parsed),
        "modules": modules,
        "imported_by": imported_by,
        "create_order_defs": [row for item in parsed for row in item.create_order_defs],
        "create_order_calls": create_order_calls,
        "src_create_order_calls": src_calls,
        "unexpected_src_create_order_calls": unexpected_src_calls,
        "buy_sell_hold": [row for item in parsed for row in item.buy_sell_hold],
        "pair_aliases": [row for item in parsed for row in item.pair_aliases],
        "other_exchanges": [row for item in parsed for row in item.other_exchanges],
        "other_exchanges_in_src": other_src,
        "bare_excepts": [row for item in parsed for row in item.bare_excepts],
        "parse_errors": [
            {"file": item.path, "error": item.parse_error}
            for item in parsed
            if item.parse_error
        ],
    }


def leftover_wiki_html(root: Path) -> list[str]:
    names: list[str] = []
    for path in sorted(root.glob("*.html")):
        names.append(rel(root, path))
    return names


def file_inventory(root: Path, ast_report: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    ast_report = ast_report or analyze_python(root)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in iter_files(root, (".py", ".sh")):
        key = rel(root, path)
        if path.suffix not in {".py", ".sh"} and path.name != "start.sh":
            continue
        if path.suffix == ".sh" and "scripts/" not in key and path.name != "start.sh":
            continue
        seen.add(key)
        meta = FILE_ROLES.get(
            key,
            {
                "role": "unclassified",
                "in_use": key.startswith("src/bitbank_bot/")
                or key.startswith("scripts/")
                or key.startswith("tests/"),
                "api": False,
                "order": False,
                "strategy": False,
                "config": False,
            },
        )
        calls = [
            row
            for row in ast_report.get("create_order_calls", [])
            if row["file"] == key
        ]
        rows.append(
            {
                "path": key,
                "role": meta["role"],
                "in_use": bool(meta["in_use"]),
                "legacy": not bool(meta["in_use"]),
                "api": bool(meta["api"]),
                "order": bool(meta["order"]) or bool(calls),
                "strategy": bool(meta["strategy"]),
                "config": bool(meta["config"]),
                "create_order_calls": len(calls),
            }
        )
    for name, meta in FILE_ROLES.items():
        if name not in seen:
            rows.append(
                {
                    "path": name,
                    "role": meta["role"],
                    "in_use": bool(meta["in_use"]),
                    "legacy": not Path(root, name).exists(),
                    "api": bool(meta["api"]),
                    "order": bool(meta["order"]),
                    "strategy": bool(meta["strategy"]),
                    "config": bool(meta["config"]),
                    "create_order_calls": 0,
                    "missing": not Path(root, name).exists(),
                }
            )
    for html in leftover_wiki_html(root):
        rows.append(
            {
                "path": html,
                "role": "leftover_wiki_html",
                "in_use": False,
                "legacy": True,
                "api": False,
                "order": False,
                "strategy": False,
                "config": False,
                "create_order_calls": 0,
                "note": "not a program; do not execute",
            }
        )
    rows.sort(key=lambda row: row["path"])
    return rows


def _redact_dump_line(line: str) -> str:
    from bitbank_bot.logging_setup import redact

    stripped = line.strip()
    if stripped.startswith(("BITBANK_API_KEY=", "BITBANK_API_SECRET=", "API_SECRET=")):
        key, _, _rest = line.partition("=")
        return f"{key}=[REDACTED]\n" if line.endswith("\n") else f"{key}=[REDACTED]"
    return redact(line)


DUMP_HEADER = """# ANALYSIS DUMP ONLY — NOT AN EXECUTABLE PROGRAM
# Do not run: python trading_bot_all_source.txt
# Secrets and .env files are excluded. Concatenation is for review.
# The runnable bot remains: bash ./start.sh  →  python -m bitbank_bot
#
"""


def dump_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for rel_name in (
        "start.sh",
        "main.py",
        "run.py",
        "diagnostics.py",
    ):
        path = root / rel_name
        if path.is_file():
            paths.append(path)
    src = root / "src" / "bitbank_bot"
    if src.is_dir():
        paths.extend(sorted(p for p in src.rglob("*.py") if p.is_file()))
    scripts = root / "scripts"
    if scripts.is_dir():
        paths.extend(sorted(p for p in scripts.iterdir() if p.suffix in {".py", ".sh"}))
    uniq: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen or is_secret_path(path):
            continue
        seen.add(resolved)
        uniq.append(path)
    return uniq


def write_source_dump(root: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    chunks = [DUMP_HEADER]
    for path in dump_paths(root):
        rel_path = rel(root, path)
        chunks.append(f"\n# SOURCE: {rel_path}\n")
        text = path.read_text(encoding="utf-8", errors="replace")
        redacted = "".join(_redact_dump_line(line) for line in text.splitlines(True))
        chunks.append(redacted)
        if not redacted.endswith("\n"):
            chunks.append("\n")
    dest.write_text("".join(chunks), encoding="utf-8")
    return dest


def write_inventory_markdown(root: Path, rows: list[dict[str, Any]], dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# File inventory",
        "",
        "Generated by `scripts/analyze_ast.py`. Wiki HTML is leftover, not a program.",
        "No Python duplicates were deleted; none were archived because none were duplicate bots.",
        "",
        "| path | role | in_use | api | order | strategy | config | notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        note = row.get("note") or ("missing" if row.get("missing") else "")
        if row.get("legacy") and row["role"] == "leftover_wiki_html":
            note = "leftover wiki HTML"
        lines.append(
            "| `{path}` | {role} | {in_use} | {api} | {order} | {strategy} | {config} | {note} |".format(
                path=row["path"],
                role=row["role"],
                in_use=row["in_use"],
                api=row["api"],
                order=row["order"],
                strategy=row["strategy"],
                config=row["config"],
                note=note,
            )
        )
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest


def completion_checks(root: Path, ast_report: dict[str, Any] | None = None) -> dict[str, Any]:
    ast_report = ast_report or analyze_python(root)
    checks: list[dict[str, Any]] = []

    def add(check_id: str, name: str, ok: bool, evidence: str, skip: bool = False) -> None:
        checks.append(
            {
                "id": check_id,
                "name": name,
                "ok": bool(ok),
                "skip": skip,
                "evidence": evidence,
            }
        )

    compile_ok = True
    compile_err = ""
    try:
        for path in (root / "src").rglob("*.py"):
            py_compile.compile(str(path), doraise=True)
        py_compile.compile(str(root / "main.py"), doraise=True)
        py_compile.compile(str(root / "run.py"), doraise=True)
    except Exception as exc:
        compile_ok = False
        compile_err = type(exc).__name__
    add("01", "python_syntax", compile_ok, compile_err or "py_compile src + main.py + run.py")
    add(
        "02",
        "ast_parse",
        not ast_report["parse_errors"],
        json.dumps(ast_report["parse_errors"]),
    )
    add(
        "03",
        "create_order_only_order_path",
        not ast_report["unexpected_src_create_order_calls"],
        json.dumps(ast_report["src_create_order_calls"]),
    )
    add(
        "04",
        "no_other_exchange_in_src",
        not ast_report["other_exchanges_in_src"],
        json.dumps(ast_report["other_exchanges_in_src"]),
    )
    add(
        "05",
        "api_facade_present",
        (root / "src" / "bitbank_bot" / "api_client.py").is_file(),
        "src/bitbank_bot/api_client.py",
    )
    add(
        "06",
        "run_py_never_create_order",
        "create_order(" not in (root / "run.py").read_text(encoding="utf-8"),
        "run.py",
    )
    cfg_text = (root / "src" / "bitbank_bot" / "config.py").read_text(encoding="utf-8")
    add("07", "pair_btc_jpy", 'PAIR = "btc_jpy"' in cfg_text, "config.PAIR")
    add(
        "08",
        "launcher_present",
        (root / "start.sh").is_file()
        and (root / "src" / "bitbank_bot" / "launch.py").is_file(),
        "start.sh + launch.py",
    )
    add(
        "09",
        "execution_gate_present",
        (root / "src" / "bitbank_bot" / "execution_gate.py").is_file(),
        "execution_gate.py",
    )
    add(
        "10",
        "no_trading_bot_rewrite_tree",
        not (root / "trading_bot").exists(),
        "did not invent trading_bot/",
    )
    add(
        "11",
        "live_post_not_claimed",
        True,
        "LIVE Bitbank POST is NOT TESTED here",
        skip=True,
    )
    scored = [row for row in checks if not row["skip"]]
    passed = sum(1 for row in scored if row["ok"])
    percent = int(round(100 * passed / len(scored))) if scored else 0
    return {
        "checks": checks,
        "passed": passed,
        "scored": len(scored),
        "skipped": sum(1 for row in checks if row["skip"]),
        "completion_percent": percent,
        "live_post": "NOT_TESTED",
    }


def write_ast_reports(root: Path, out_dir: Path | None = None) -> int:
    out_dir = out_dir or (root / "reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    ast_report = analyze_python(root)
    inventory = file_inventory(root, ast_report)
    graph = {
        "modules": {
            path: {"imports": meta["imports"]}
            for path, meta in ast_report["modules"].items()
        },
        "imported_by": ast_report["imported_by"],
    }
    (out_dir / "dependency_graph.json").write_text(
        json.dumps(graph, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / "ast_report.json").write_text(
        json.dumps(ast_report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / "file_inventory.json").write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_inventory_markdown(root, inventory, out_dir / "FILE_INVENTORY.md")
    spec = completion_checks(root, ast_report)
    (out_dir / "completion_spec.json").write_text(
        json.dumps(spec, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0 if spec["passed"] == spec["scored"] and not ast_report["parse_errors"] else 1


def write_dump(root: Path, dest: Path | None = None) -> Path:
    dest = dest or (root / "reports" / "trading_bot_all_source.txt")
    return write_source_dump(root, dest)
