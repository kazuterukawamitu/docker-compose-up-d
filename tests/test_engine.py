import json
import time
from pathlib import Path

from bitbank_bot.engine import BotState, Engine, load_state, save_state
from bitbank_bot.money import D
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import Signal

from helpers import cfg


def _engine_cfg(tmp_path: Path, **kwargs):
    return cfg(
        dry_run=True,
        simulate_fill=True,
        enable_websocket=False,
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        kill_switch_path=str(tmp_path / "KILL"),
        dry_run_free_jpy=D("100000"),
        dry_run_free_btc=D("0"),
        **kwargs,
    )


def _buy_signal() -> Signal:
    return Signal("BUY1", "buy", D("0.03"), "test buy")


def test_buy_executes_when_kill_switch_off(tmp_path: Path) -> None:
    c = _engine_cfg(tmp_path, kill_switch=False)
    engine = Engine(c)
    state = BotState(None, RiskManager(c, killed=False), 0, time.monotonic())
    engine._execute(_buy_signal(), D("10000000"), 10, 1_700_000_000_000, state)
    assert engine.stats.order_attempts == 1
    assert engine.stats.last_block_reason == ""
    assert state.position is not None
    assert state.position.amount > D("0")


def test_buy_blocked_when_kill_switch_on(tmp_path: Path) -> None:
    c = _engine_cfg(tmp_path, kill_switch=True)
    engine = Engine(c)
    state = BotState(None, RiskManager(c), 0, time.monotonic())
    engine._execute(_buy_signal(), D("10000000"), 10, 1_700_000_000_000, state)
    assert engine.stats.order_attempts == 0
    assert engine.stats.last_block_reason == "kill_switch"
    assert state.position is None


def test_stale_state_kill_switch_does_not_latch(tmp_path: Path) -> None:
    c = _engine_cfg(tmp_path, kill_switch=False)
    path = Path(c.state_path)
    path.write_text(
        json.dumps(
            {
                "daily_pnl": "0",
                "daily_pnl_date": "2026-08-30",
                "kill_switch": True,
                "last_candle_ts": 0,
                "position": None,
            }
        ),
        encoding="utf-8",
    )
    state = load_state(path, c)
    assert not state.risk.operator_killed
    decision = state.risk.check_buy(D("0"), D("0.1"))
    assert decision.allowed
    assert decision.reason == "ok"
    engine = Engine(c)
    engine._execute(_buy_signal(), D("10000000"), 10, 1_700_000_000_000, state)
    assert engine.stats.order_attempts == 1
    assert engine.stats.last_block_reason != "kill_switch"
    save_state(path, state)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["kill_switch"] is False
    assert payload["operator_killed"] is False


def test_successful_fill_clears_prior_block_reason(tmp_path: Path) -> None:
    c = _engine_cfg(tmp_path, kill_switch=False)
    engine = Engine(c)
    engine.stats.last_block_reason = "kill_switch"
    state = BotState(None, RiskManager(c, killed=False), 0, time.monotonic())
    engine._execute(_buy_signal(), D("10000000"), 10, 1_700_000_000_000, state)
    assert engine.stats.order_attempts == 1
    assert engine.stats.last_block_reason == ""
