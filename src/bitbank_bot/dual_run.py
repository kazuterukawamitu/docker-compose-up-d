"""V31 production + OOS shadow evaluators.

Existing ``v31.py`` / ``oos.py`` plugins are discovered if present. They are
not invented here. OOS / shadow never receive an order client.
"""

from __future__ import annotations

import ast
import importlib.util
import logging
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Protocol

from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.strategy import MarketSnapshot, Position, Signal, Strategy

_LOG = logging.getLogger("bitbank_bot")

FORBIDDEN_NAMES = frozenset(
    {
        "create_order",
        "private_post",
        "OrderExecutor",
    }
)
FORBIDDEN_SUBSTRINGS = ("/user/spot/order",)
PLUGIN_FILENAMES = {
    "v31": ("v31.py", "src/v31.py", "src/bitbank_bot/v31.py"),
    "oos": ("oos.py", "src/oos.py", "src/bitbank_bot/oos.py"),
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


class SignalEvaluator(Protocol):
    def observe(self, snap: MarketSnapshot) -> None: ...

    def evaluate(self, snap: MarketSnapshot, position: Position | None) -> Signal: ...


def scan_plugin_source(source: str) -> list[str]:
    """Return reasons a plugin must not be imported or given order authority."""
    reasons: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"syntax_error:{exc.msg}"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            reasons.append(f"name:{node.id}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in FORBIDDEN_NAMES:
                reasons.append(f"name:{node.name}")
        elif isinstance(node, ast.arg) and node.arg in FORBIDDEN_NAMES:
            reasons.append(f"name:{node.arg}")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES:
            reasons.append(f"attr:{node.attr}")
        elif isinstance(node, ast.alias) and (node.name in FORBIDDEN_NAMES or node.asname in FORBIDDEN_NAMES):
            reasons.append(f"name:{node.name}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for needle in FORBIDDEN_SUBSTRINGS:
                if needle in node.value:
                    reasons.append("spot_order_path")
    # unique, stable
    seen: list[str] = []
    for item in reasons:
        if item not in seen:
            seen.append(item)
    return seen


def _load_module(path: Path, mod_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass
class PluginHit:
    kind: str
    path: Path | None
    status: str
    safe: bool
    reasons: list[str] = field(default_factory=list)
    module: ModuleType | None = field(default=None, repr=False)

    def safe_dict(self) -> dict[str, object]:
        rel = None
        if self.path is not None:
            try:
                rel = str(self.path.resolve().relative_to(repo_root()))
            except ValueError:
                rel = self.path.name
        return {
            "kind": self.kind,
            "path": rel,
            "status": self.status,
            "safe": self.safe,
            "reasons": list(self.reasons),
        }


class CallableEvaluator:
    def __init__(self, fn: Callable[..., Signal], name: str) -> None:
        self._fn = fn
        self.name = name

    def observe(self, snap: MarketSnapshot) -> None:
        return None

    def evaluate(self, snap: MarketSnapshot, position: Position | None) -> Signal:
        return self._fn(snap, position)


class ShadowStrategy:
    """No-order evaluator using README Strategy when oos.py is Not Detected."""

    def __init__(self, cfg: Config) -> None:
        self._inner = Strategy(cfg)
        self.name = "strategy_shadow"

    def observe(self, snap: MarketSnapshot) -> None:
        self._inner.observe(snap)

    def evaluate(self, snap: MarketSnapshot, position: Position | None) -> Signal:
        return self._inner.evaluate(snap, position)


def discover_plugin(kind: str, root: Path | None = None) -> PluginHit:
    if kind not in PLUGIN_FILENAMES:
        raise ValueError(f"unknown plugin kind {kind}")
    base = root or repo_root()
    found: Path | None = None
    for rel in PLUGIN_FILENAMES[kind]:
        candidate = base / rel
        if candidate.is_file():
            found = candidate
            break
    if found is None:
        return PluginHit(kind, None, "Not Detected", True, [])
    source = found.read_text(encoding="utf-8")
    reasons = scan_plugin_source(source)
    if reasons:
        slog(
            "DUAL_RUN",
            f"{kind} plugin refused (order-path names)",
            kind=kind,
            reasons=reasons,
        )
        return PluginHit(kind, found, "unsafe", False, reasons)
    try:
        module = _load_module(found, f"bitbank_bot_plugin_{kind}")
    except Exception as exc:
        _LOG.exception("plugin import failed")
        return PluginHit(kind, found, "import_error", False, [type(exc).__name__])
    return PluginHit(kind, found, "loaded", True, [], module)


def _evaluator_from_plugin(hit: PluginHit, cfg: Config, role: str) -> SignalEvaluator | None:
    module = hit.module
    if module is None or not hit.safe or hit.status != "loaded":
        return None
    strat_cls = getattr(module, "Strategy", None)
    if isinstance(strat_cls, type):
        try:
            inst = strat_cls(cfg)  # type: ignore[call-arg]
        except TypeError:
            inst = strat_cls()  # type: ignore[call-arg]
        if hasattr(inst, "evaluate"):
            slog("DUAL_RUN", f"{role} using plugin Strategy", kind=hit.kind)
            return inst  # type: ignore[return-value]
    fn = getattr(module, "evaluate", None)
    if callable(fn):
        slog("DUAL_RUN", f"{role} using plugin evaluate()", kind=hit.kind)
        return CallableEvaluator(fn, f"{hit.kind}_evaluate")
    slog("DUAL_RUN", f"{hit.kind} loaded but incompatible; not wired", role=role)
    return None


@dataclass
class DualRun:
    v31: PluginHit
    oos: PluginHit
    production_name: str = "strategy"
    shadow_name: str = "strategy_shadow"
    last_shadow: Signal | None = None
    shadow_evaluations: int = 0
    oos_tuning_applied: bool = False
    oos_proposals: list[str] = field(default_factory=list)

    @classmethod
    def discover(cls, root: Path | None = None) -> "DualRun":
        v31 = discover_plugin("v31", root)
        oos = discover_plugin("oos", root)
        production_name = "v31" if v31.status == "loaded" and v31.safe else "strategy"
        if oos.status == "loaded" and oos.safe:
            shadow_name = "oos"
        else:
            shadow_name = "strategy_shadow"
        slog(
            "DUAL_RUN",
            "discover",
            v31=v31.status,
            oos=oos.status,
            production=production_name,
            shadow=shadow_name,
            oos_execute=False,
        )
        return cls(
            v31=v31,
            oos=oos,
            production_name=production_name,
            shadow_name=shadow_name,
        )

    def make_production(self, cfg: Config) -> SignalEvaluator:
        if self.v31.status == "loaded" and self.v31.safe:
            wired = _evaluator_from_plugin(self.v31, cfg, "production")
            if wired is not None:
                self.production_name = getattr(wired, "name", "v31")
                return wired
            self.production_name = "strategy"
            slog("DUAL_RUN", "V31 not wired; production stays Strategy")
        return Strategy(cfg)

    def make_shadow(self, cfg: Config) -> SignalEvaluator:
        if self.oos.status == "loaded" and self.oos.safe:
            wired = _evaluator_from_plugin(self.oos, cfg, "shadow")
            if wired is not None:
                self.shadow_name = getattr(wired, "name", "oos")
                return wired
        self.shadow_name = "strategy_shadow"
        return ShadowStrategy(cfg)

    def note_shadow(self, signal: Signal) -> None:
        self.last_shadow = signal
        self.shadow_evaluations += 1
        proposal = getattr(signal, "reason", "") or ""
        if proposal.startswith("oos_tune:") or proposal.startswith("tune:"):
            self.oos_proposals.append(proposal)
            slog(
                "OOS_SHADOW",
                "tuning proposal ignored",
                proposal=proposal[:120],
                applied=False,
            )

    def shadow_has_order_authority(self) -> bool:
        return False

    def safe_status(self) -> dict[str, object]:
        return {
            "v31": self.v31.safe_dict(),
            "oos": self.oos.safe_dict(),
            "production": self.production_name,
            "shadow": self.shadow_name,
            "oos_execute": False,
            "oos_create_order": False,
            "oos_tuning_applied": self.oos_tuning_applied,
            "shadow_evaluations": self.shadow_evaluations,
            "last_shadow_kind": None if self.last_shadow is None else self.last_shadow.kind,
            "last_shadow_reason": None if self.last_shadow is None else self.last_shadow.reason,
        }


def refuse_create_order(*_args: Any, **_kwargs: Any) -> None:
    raise RuntimeError("OOS/shadow/guard must not call create_order")
