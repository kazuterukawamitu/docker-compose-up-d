from __future__ import annotations

import os

from bitbank_bot.loop_timers import LoopEvidence, ShadowGuardTimers, pid_is_alive
from tests.helpers import cfg


def test_env_yes_is_not_activation() -> None:
    loop = LoopEvidence()
    timers = ShadowGuardTimers(
        loop, environ={"SHADOW_TIMER": "yes", "GUARD_TIMER": "yes"}
    )
    shadow, guard = timers.refresh()
    assert shadow.requested_by_env is True
    assert guard.requested_by_env is True
    assert shadow.enabled is False
    assert shadow.active is False
    assert guard.active is False
    assert "env_flag_ignored_no_running_loop" in shadow.evidence


def test_timers_active_only_with_loop_cycle() -> None:
    loop = LoopEvidence()
    loop.begin(pid=os.getpid(), poll_sec=1.0)
    timers = ShadowGuardTimers(loop, environ={"SHADOW_TIMER": "yes"})
    shadow, _guard = timers.refresh()
    assert shadow.active is False
    loop.note_cycle()
    shadow, guard = timers.refresh()
    assert loop.loop_alive() is True
    assert shadow.active is True
    assert guard.active is True
    assert "cycle=" in shadow.evidence
    loop.end()
    shadow, guard = timers.refresh()
    assert shadow.active is False
    assert guard.active is False


def test_stale_cycle_is_not_alive() -> None:
    loop = LoopEvidence()
    loop.begin(pid=os.getpid(), poll_sec=1.0)
    loop.note_cycle(now=0.0)
    assert loop.loop_alive(now=10.0) is False


def test_pid_is_alive_self() -> None:
    assert pid_is_alive(os.getpid()) is True
    assert pid_is_alive(-1) is False


def test_guard_tick_logs_no_oos_orders() -> None:
    from bitbank_bot.dual_run import DualRun

    loop = LoopEvidence()
    loop.begin(pid=os.getpid(), poll_sec=1.0)
    loop.note_cycle()
    timers = ShadowGuardTimers(loop)
    state = timers.tick_guard(cfg(dry_run=True, live_trading=False), DualRun.discover())
    assert state.active is True
    assert DualRun.discover().shadow_has_order_authority() is False
