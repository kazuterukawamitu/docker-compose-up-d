"""Gap detection versus completion criteria. Never places orders. No secrets."""

from __future__ import annotations

import ast
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bitbank_bot.config import load_config
from bitbank_bot.dual_run import DualRun, repo_root, scan_plugin_source
from bitbank_bot.evidence import report_flags
from bitbank_bot.loop_timers import LoopEvidence, ShadowGuardTimers

SECRET_VALUE = re.compile(r"\b[0-9a-f]{64}\b", re.IGNORECASE)
SECRET_ASSIGN = re.compile(
    r"(BITBANK_API_SECRET|API_SECRET|ACCESS-SIGNATURE)\s*[:=]\s*['\"][^'\"]+['\"]",
    re.IGNORECASE,
)


@dataclass
class Criterion:
    id: str
    status: str
    evidence: str

    def as_dict(self) -> dict[str, str]:
        return {"id": self.id, "status": self.status, "evidence": self.evidence}


@dataclass
class GapReport:
    criteria: list[Criterion] = field(default_factory=list)
    flags: dict[str, Any] = field(default_factory=dict)
    generated_at: str = ""
    live: str = "NO"
    has_secret_values: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "LIVE": self.live,
            "has_secret_values": self.has_secret_values,
            "criteria": [c.as_dict() for c in self.criteria],
            "flags": self.flags,
        }


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _docker_secret_leaks(root: Path) -> list[str]:
    leaks: list[str] = []
    for rel in (
        "docker/Dockerfile.audit",
        "docker/compose.audit.yml",
        "docker/compose.dry-run.yml",
        ".dockerignore",
        "docker/.dockerignore",
    ):
        text = _text(root / rel)
        if not text:
            if rel in {"docker/Dockerfile.audit", "docker/compose.audit.yml"}:
                leaks.append(f"missing:{rel}")
            continue
        if re.search(r"(?m)^\s*env_file\s*:", text):
            leaks.append(f"{rel}:env_file")
        if re.search(r"(?i)COPY\s+\.env\b", text):
            leaks.append(f"{rel}:copy_.env")
        if re.search(r"(?i)BITBANK_API_SECRET\s*[:=]\s*\S+", text):
            leaks.append(f"{rel}:secret_name")
    return leaks


def _shadow_guard_no_orders(root: Path) -> bool:
    paths = [
        root / "src" / "bitbank_bot" / "loop_timers.py",
        root / "docker" / "audit_agent.py",
        root / "docker" / "healthcheck.py",
    ]
    for path in paths:
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in {
                    "create_order",
                    "private_post",
                }:
                    return False
                if isinstance(func, ast.Name) and func.id in {
                    "create_order",
                    "private_post",
                }:
                    return False
    return True


def run_gap_audit(root: Path | None = None) -> GapReport:
    base = root or repo_root()
    generated = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # Never load host .env / keys. Force DRY_RUN for this process snapshot.
    cfg = load_config(
        environ={"DRY_RUN": "true", "LIVE_TRADING": "false"},
        load_default_dotenv=False,
    )
    dual = DualRun.discover(base)
    dual.probe(cfg)
    loop = LoopEvidence()
    timers = ShadowGuardTimers(
        loop,
        environ={"SHADOW_TIMER": "yes", "GUARD_TIMER": "yes"},
    )
    fake_yes = timers.status_dict()
    flags = report_flags(cfg, dual=dual, loop=loop, timers=timers, root=base)

    criteria: list[Criterion] = []

    def add(cid: str, status: str, evidence: str) -> None:
        criteria.append(Criterion(cid, status, evidence))

    add(
        "pair",
        "PASS" if cfg.pair == "btc_jpy" else "FAIL",
        f"pair={cfg.pair}",
    )
    add(
        "live_default",
        "PASS" if (cfg.dry_run and not cfg.live_trading and not cfg.may_place_live_orders) else "FAIL",
        f"dry_run={cfg.dry_run} live_trading={cfg.live_trading} may_place={cfg.may_place_live_orders}",
    )
    host_live = (os.environ.get("LIVE_TRADING") or "").strip().lower()
    add(
        "host_live_env",
        "PASS" if host_live in {"", "false", "0", "no", "off"} else "PARTIAL",
        f"host_LIVE_TRADING={host_live or 'unset'}; audit load_config forced DRY_RUN",
    )

    rest_src = _text(base / "src" / "bitbank_bot" / "rest_client.py")
    add(
        "create_order_gate",
        "PASS" if "live_confirmed" in rest_src else "FAIL",
        "RestClient.create_order requires live_confirmed",
    )

    v31_st = dual.v31.status
    if v31_st == "Not Detected":
        add("v31_plugin", "NOT_VERIFIED", "v31.py Not Detected; production stays Strategy")
    elif dual.v31_wired:
        add("v31_plugin", "PASS", f"wired production={dual.production_name}")
    elif v31_st == "unsafe":
        add("v31_plugin", "FAIL", f"refused {dual.v31.reasons}")
    elif v31_st == "loaded":
        add(
            "v31_plugin",
            "PARTIAL",
            f"loaded but not wired; production={dual.production_name}",
        )
    else:
        add("v31_plugin", "PARTIAL", v31_st)

    oos_st = dual.oos.status
    if oos_st == "Not Detected":
        add(
            "oos_plugin",
            "NOT_VERIFIED",
            "oos.py Not Detected; strategy_shadow evaluator only (no orders)",
        )
    elif dual.oos_wired:
        add("oos_plugin", "PASS", f"shadow={dual.shadow_name} execute=false")
    elif oos_st == "unsafe":
        add("oos_plugin", "FAIL", f"refused {dual.oos.reasons}")
    elif oos_st == "loaded":
        add(
            "oos_plugin",
            "PARTIAL",
            f"loaded but not wired; shadow={dual.shadow_name}",
        )
    else:
        add("oos_plugin", "PARTIAL", oos_st)

    add(
        "oos_no_create_order",
        "PASS" if not dual.shadow_has_order_authority() else "FAIL",
        "shadow_has_order_authority=false",
    )
    add(
        "shadow_guard_source",
        "PASS" if _shadow_guard_no_orders(base) else "FAIL",
        "loop_timers/audit_agent/healthcheck have no create_order call",
    )

    shadow_active = bool(fake_yes["shadow"]["active"])
    guard_active = bool(fake_yes["guard"]["active"])
    add(
        "shadow_timer_no_fake_yes",
        "PASS" if not shadow_active else "FAIL",
        f"SHADOW_TIMER=yes without loop -> active={shadow_active} evidence={fake_yes['shadow']['evidence']}",
    )
    add(
        "guard_timer_no_fake_yes",
        "PASS" if not guard_active else "FAIL",
        f"GUARD_TIMER=yes without loop -> active={guard_active} evidence={fake_yes['guard']['evidence']}",
    )

    engine_src = _text(base / "src" / "bitbank_bot" / "engine.py")
    add(
        "dual_run_wired",
        "PASS" if "make_shadow" in engine_src and "make_production" in engine_src else "FAIL",
        "Engine.process_candles uses DualRun production+shadow",
    )

    leaks = _docker_secret_leaks(base)
    dockerfile = _text(base / "docker" / "Dockerfile.audit")
    compose = _text(base / "docker" / "compose.audit.yml")
    dry = _text(base / "docker" / "compose.dry-run.yml")
    dockerignore = _text(base / ".dockerignore")
    add(
        "docker_audit_files",
        "PASS" if dockerfile and compose and "healthcheck" in compose.lower() else "FAIL",
        "Dockerfile.audit + compose.audit.yml healthcheck",
    )
    add(
        "docker_no_secrets",
        "PASS" if not leaks else "FAIL",
        "ok" if not leaks else ",".join(leaks),
    )
    add(
        "docker_dry_run",
        "PASS"
        if 'DRY_RUN=true' in dockerfile.replace(" ", "") or "DRY_RUN: \"true\"" in compose or "DRY_RUN: 'true'" in compose
        else "PARTIAL",
        "audit image/compose force DRY_RUN=true LIVE_TRADING=false",
    )
    add(
        "dockerignore_env",
        "PASS" if ".env" in dockerignore else "FAIL",
        ".dockerignore excludes .env",
    )
    add(
        "compose_dry_run_pytest",
        "PASS" if dry and "DRY_RUN" in dry and "env_file:" not in dry else "FAIL",
        "docker/compose.dry-run.yml pytest DRY_RUN only",
    )

    quality = base / "scripts" / "quality_pipeline.py"
    workflow = _text(base / ".github" / "workflows" / "main.yml")
    add(
        "quality_pipeline",
        "PASS" if quality.is_file() else "FAIL",
        "scripts/quality_pipeline.py compileall+pytest+ruff",
    )
    add(
        "ci_ruff",
        "PASS" if "ruff" in workflow else "PARTIAL",
        "CI workflow includes ruff check (safe select)",
    )

    sample = "def create_order():\n    pass\n"
    add(
        "plugin_scan_blocks_orders",
        "PASS" if "name:create_order" in scan_plugin_source(sample) else "FAIL",
        "scan_plugin_source flags create_order",
    )

    blob = json.dumps(flags, default=str)
    has_secrets = bool(SECRET_VALUE.search(blob) or SECRET_ASSIGN.search(blob))
    add(
        "no_secrets_in_report",
        "FAIL" if has_secrets else "PASS",
        "report JSON has no 64-hex secrets or assigned API secrets",
    )

    live_status = str(flags.get("flags", {}).get("LIVE", {}).get("status") or "NO")
    report = GapReport(
        criteria=criteria,
        flags=flags,
        generated_at=generated,
        live=live_status,
        has_secret_values=has_secrets,
    )
    return report
