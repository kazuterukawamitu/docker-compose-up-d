from __future__ import annotations

from bitbank_bot.config import load_config
from bitbank_bot.dual_run import DualRun
from bitbank_bot.evidence import report_flags
from bitbank_bot.loop_timers import LoopEvidence, ShadowGuardTimers


def test_live_private_order_oos_tuning_are_no_without_evidence() -> None:
    cfg = load_config(environ={"DRY_RUN": "true", "LIVE_TRADING": "false"}, load_default_dotenv=False)
    flags = report_flags(cfg, dual=DualRun.discover(), loop=LoopEvidence())
    body = flags["flags"]
    assert body["LIVE"]["status"] == "NO"
    assert body["private_api"]["status"] == "NO"
    assert body["order_create"]["status"] == "NO"
    assert body["oos_tuning"]["status"] == "NO"
    assert body["oos_create_order"]["status"] == "NO"
    assert body["v31_module"]["status"] == "YES"
    assert body["oos_module"]["status"] == "YES"
    assert "v31_strategy" in body["v31_module"]["evidence"]
    assert "oos_shadow" in body["oos_module"]["evidence"]
    assert body["shadow_timer"]["status"] == "NO"
    assert body["guard_timer"]["status"] == "NO"
    dumped = str(flags)
    assert "BITBANK_API_SECRET" not in dumped
    assert cfg.api_secret == ""


def test_safe_dict_still_hides_secrets() -> None:
    cfg = load_config(
        environ={
            "DRY_RUN": "true",
            "BITBANK_API_KEY": "k",
            "BITBANK_API_SECRET": "s" * 16,
        },
        load_default_dotenv=False,
    )
    flags = report_flags(cfg)
    assert "s" * 16 not in str(flags)
    assert flags["has_api_key"] is True
    assert flags["flags"]["private_api"]["status"] == "NOT_VERIFIED"


def test_loop_flips_timer_flags_without_env() -> None:
    cfg = load_config(environ={}, load_default_dotenv=False)
    loop = LoopEvidence()
    loop.begin(pid=1, poll_sec=1.0)
    loop.note_cycle()
    timers = ShadowGuardTimers(loop, environ={})
    flags = report_flags(cfg, loop=loop, timers=timers)
    assert flags["flags"]["shadow_timer"]["status"] == "YES"
    assert flags["flags"]["guard_timer"]["status"] == "YES"
    assert flags["flags"]["LIVE"]["status"] == "NO"
