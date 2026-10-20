"""Evidence-based LIVE / private-API / order-create / OOS-tuning flags.

A YES is never inferred from an env slogan. LIVE stays NO without dual
confirm plus keys. This module does not write ``.env`` and does not print
secrets.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from bitbank_bot.config import Config
from bitbank_bot.dual_run import DualRun, repo_root
from bitbank_bot.loop_timers import LoopEvidence, ShadowGuardTimers


@dataclass(frozen=True)
class Flag:
    name: str
    status: str
    evidence: str

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "evidence": self.evidence}


def _source_create_order_gated(root: Path | None = None) -> tuple[bool, str]:
    base = root or repo_root()
    rest = (base / "src" / "bitbank_bot" / "rest_client.py").read_text(encoding="utf-8")
    orders = (base / "src" / "bitbank_bot" / "orders.py").read_text(encoding="utf-8")
    rest_ok = "live_confirmed" in rest and "refusing create_order without live_confirmed" in rest
    orders_ok = "may_place_live_orders" in orders
    return rest_ok and orders_ok, (
        "rest_client.create_order requires live_confirmed; "
        "OrderExecutor.place gated on may_place_live_orders"
        if rest_ok and orders_ok
        else "create_order gate source missing"
    )


def _source_has_create_order_call(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "create_order":
                return True
            if isinstance(func, ast.Name) and func.id == "create_order":
                return True
    return False


def report_flags(
    cfg: Config,
    *,
    dual: DualRun | None = None,
    loop: LoopEvidence | None = None,
    timers: ShadowGuardTimers | None = None,
    create_order_posts: int = 0,
    private_get_ok: bool = False,
    root: Path | None = None,
) -> dict[str, object]:
    dual = dual or DualRun.discover(root)
    loop = loop or LoopEvidence()
    timers = timers or ShadowGuardTimers(loop)
    timers.refresh()

    if cfg.may_place_live_orders:
        live = Flag(
            "LIVE",
            "YES",
            "may_place_live_orders true (DRY_RUN=false and LIVE_TRADING=true and keys)",
        )
    else:
        live = Flag(
            "LIVE",
            "NO",
            (
                f"dry_run={cfg.dry_run} live_trading={cfg.live_trading} "
                f"has_keys={cfg.has_keys} may_place_live_orders={cfg.may_place_live_orders}"
            ),
        )

    if private_get_ok:
        private = Flag("private_api", "YES", "private GET succeeded this process")
    elif cfg.has_keys:
        private = Flag(
            "private_api",
            "NOT_VERIFIED",
            "has_keys true; no private GET observed this process",
        )
    else:
        private = Flag("private_api", "NO", "keys absent; private REST not used")

    gated, gate_note = _source_create_order_gated(root)
    if create_order_posts > 0:
        order = Flag(
            "order_create",
            "YES",
            f"create_order posted count={create_order_posts}",
        )
    elif gated:
        order = Flag("order_create", "NO", f"{gate_note}; posts=0 this process")
    else:
        order = Flag("order_create", "FAIL", gate_note)

    if dual.oos_tuning_applied:
        tuning = Flag("oos_tuning", "YES", "OOS-tuned params applied to production (unexpected)")
    elif dual.oos_proposals:
        tuning = Flag(
            "oos_tuning",
            "NO",
            f"proposals={len(dual.oos_proposals)} applied=false",
        )
    else:
        tuning = Flag(
            "oos_tuning",
            "NO",
            f"oos_plugin={dual.oos.status}; no proposals; production cfg unchanged",
        )

    shadow_mods = [
        repo_root() / "src" / "bitbank_bot" / "loop_timers.py",
        repo_root() / "src" / "bitbank_bot" / "dual_run.py",
        repo_root() / "src" / "bitbank_bot" / "evidence.py",
    ]
    oos_calls = any(p.is_file() and _source_has_create_order_call(p) for p in shadow_mods)
    oos_auth = Flag(
        "oos_create_order",
        "FAIL" if oos_calls or dual.shadow_has_order_authority() else "NO",
        "OOS/shadow/guard source has no create_order call; authority=false",
    )

    v31_status = dual.v31.status
    if v31_status == "Not Detected":
        v31_flag = Flag("v31_module", "NOT_VERIFIED", "v31.py Not Detected; production=Strategy")
    elif v31_status == "loaded" and dual.production_name != "strategy":
        v31_flag = Flag("v31_module", "YES", f"wired production={dual.production_name}")
    elif v31_status == "unsafe":
        v31_flag = Flag("v31_module", "FAIL", f"refused:{dual.v31.reasons}")
    else:
        v31_flag = Flag("v31_module", "PARTIAL", f"status={v31_status} production={dual.production_name}")

    if dual.oos.status == "Not Detected":
        oos_flag = Flag(
            "oos_module",
            "NOT_VERIFIED",
            "oos.py Not Detected; shadow evaluator=strategy_shadow (no orders)",
        )
    elif dual.oos.status == "loaded":
        oos_flag = Flag("oos_module", "YES", f"shadow={dual.shadow_name} execute=false")
    elif dual.oos.status == "unsafe":
        oos_flag = Flag("oos_module", "FAIL", f"refused:{dual.oos.reasons}")
    else:
        oos_flag = Flag("oos_module", "PARTIAL", dual.oos.status)

    flags = {
        "LIVE": live,
        "private_api": private,
        "order_create": order,
        "oos_tuning": tuning,
        "oos_create_order": oos_auth,
        "v31_module": v31_flag,
        "oos_module": oos_flag,
        "shadow_timer": Flag(
            "shadow_timer",
            "YES" if timers.shadow.active else "NO",
            timers.shadow.evidence,
        ),
        "guard_timer": Flag(
            "guard_timer",
            "YES" if timers.guard.active else "NO",
            timers.guard.evidence,
        ),
    }
    return {
        "flags": {k: v.as_dict() for k, v in flags.items()},
        "dual_run": dual.safe_status(),
        "timers": timers.status_dict(),
        "loop_alive": loop.loop_alive(),
        "has_api_key": cfg.has_keys,
        "dry_run": cfg.dry_run,
        "live_trading": cfg.live_trading,
        "may_place_live_orders": cfg.may_place_live_orders,
    }
