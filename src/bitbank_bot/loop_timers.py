"""Shadow and guard timers: active only with a live engine loop.

``SHADOW_TIMER=yes`` / ``GUARD_TIMER=yes`` in the environment is not
evidence. Those flags are recorded as requested-by-env and ignored until
``LoopEvidence`` shows a running ``run_forever`` cycle.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from bitbank_bot.config import Config
from bitbank_bot.dual_run import DualRun
from bitbank_bot.logging_setup import slog


def _env_yes(name: str, environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    raw = (env.get(name) or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def lock_pid(path: str | Path) -> int | None:
    p = Path(path)
    if not p.is_file():
        return None
    try:
        text = p.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return None
    if not text:
        return None
    try:
        return int(text[0].strip())
    except ValueError:
        return None


@dataclass
class LoopEvidence:
    pid: int = 0
    running: bool = False
    cycle: int = 0
    last_cycle_at: float | None = None
    poll_sec: float = 15.0
    lock_path: str = ""
    lock_pid_alive: bool | None = None

    def begin(self, *, pid: int, poll_sec: float, lock_path: str = "") -> None:
        self.pid = pid
        self.running = True
        self.poll_sec = max(0.05, float(poll_sec))
        self.lock_path = lock_path
        self.cycle = 0
        self.last_cycle_at = None

    def end(self) -> None:
        self.running = False

    def note_cycle(self, now: float | None = None) -> None:
        self.cycle += 1
        self.last_cycle_at = time.monotonic() if now is None else now
        if self.lock_path:
            held = lock_pid(self.lock_path)
            if held is None or (self.pid and held != self.pid):
                self.lock_pid_alive = None
            else:
                self.lock_pid_alive = pid_is_alive(held)
        else:
            self.lock_pid_alive = None

    def loop_alive(self, now: float | None = None) -> bool:
        if not self.running or self.cycle < 1 or self.last_cycle_at is None:
            return False
        stamp = time.monotonic() if now is None else now
        max_age = max(1.0, self.poll_sec * 3.0)
        if stamp - self.last_cycle_at > max_age:
            return False
        return True

    def evidence_text(self, now: float | None = None) -> str:
        if not self.running:
            return "loop_not_running"
        if self.cycle < 1 or self.last_cycle_at is None:
            return "loop_started_no_cycle"
        stamp = time.monotonic() if now is None else now
        age = stamp - self.last_cycle_at
        lock_bit = "lock_unchecked"
        if self.lock_pid_alive is True:
            lock_bit = "lock_pid_alive"
        elif self.lock_pid_alive is False:
            lock_bit = "lock_pid_dead"
        return (
            f"pid={self.pid} cycle={self.cycle} last_cycle_age_sec={age:.3f} {lock_bit}"
        )


@dataclass
class TimerState:
    name: str
    requested_by_env: bool
    enabled: bool
    active: bool
    evidence: str

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "requested_by_env": self.requested_by_env,
            "enabled": self.enabled,
            "active": self.active,
            "evidence": self.evidence,
        }


class ShadowGuardTimers:
    def __init__(
        self,
        loop: LoopEvidence,
        *,
        environ: dict[str, str] | None = None,
    ) -> None:
        self.loop = loop
        self._environ = environ
        self.shadow = self._inactive("shadow")
        self.guard = self._inactive("guard")

    def _requested(self, name: str) -> bool:
        env_key = "SHADOW_TIMER" if name == "shadow" else "GUARD_TIMER"
        return _env_yes(env_key, self._environ)

    def _inactive(self, name: str) -> TimerState:
        requested = self._requested(name)
        evidence = self.loop.evidence_text()
        if requested:
            evidence = f"env_flag_ignored_no_running_loop; {evidence}"
        return TimerState(
            name=name,
            requested_by_env=requested,
            enabled=False,
            active=False,
            evidence=evidence,
        )

    def refresh(self, now: float | None = None) -> tuple[TimerState, TimerState]:
        alive = self.loop.loop_alive(now)
        evidence = self.loop.evidence_text(now)
        for name in ("shadow", "guard"):
            requested = self._requested(name)
            if alive:
                note = evidence
                if requested:
                    note = f"loop_evidence; env_yes_not_used_as_proof; {evidence}"
                state = TimerState(
                    name=name,
                    requested_by_env=requested,
                    enabled=True,
                    active=True,
                    evidence=note,
                )
            else:
                note = evidence
                if requested:
                    note = f"env_flag_ignored_no_running_loop; {evidence}"
                state = TimerState(
                    name=name,
                    requested_by_env=requested,
                    enabled=False,
                    active=False,
                    evidence=note,
                )
            if name == "shadow":
                self.shadow = state
            else:
                self.guard = state
        return self.shadow, self.guard

    def tick_shadow(self, now: float | None = None) -> TimerState:
        self.refresh(now)
        slog(
            "SHADOW_TIMER",
            "tick" if self.shadow.active else "inactive",
            **self.shadow.as_dict(),
        )
        return self.shadow

    def tick_guard(
        self,
        cfg: Config,
        dual: DualRun,
        now: float | None = None,
    ) -> TimerState:
        self.refresh(now)
        payload = self.guard.as_dict()
        payload.update(
            {
                "live_orders": cfg.may_place_live_orders,
                "dry_run": cfg.dry_run,
                "live_trading": cfg.live_trading,
                "oos_create_order": dual.shadow_has_order_authority(),
                "kill_switch": cfg.kill_switch,
            }
        )
        slog(
            "GUARD_TIMER",
            "tick" if self.guard.active else "inactive",
            **payload,
        )
        if self.guard.active and cfg.may_place_live_orders:
            slog(
                "GUARD_TIMER",
                "LIVE dual-confirm present; guard still does not place orders",
            )
        return self.guard

    def status_dict(self) -> dict[str, object]:
        self.refresh()
        return {"shadow": self.shadow.as_dict(), "guard": self.guard.as_dict()}
