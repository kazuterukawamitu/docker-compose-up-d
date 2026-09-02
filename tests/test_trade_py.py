"""stdlib trade.py must run and must not POST without live=True."""
from __future__ import annotations

import compileall
import importlib.util
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRADE = ROOT / "trade.py"


def load_trade():
    spec = importlib.util.spec_from_file_location("bitbank_trade_mod", TRADE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_trade_py_compiles() -> None:
    assert compileall.compile_file(str(TRADE), quiet=1)


def test_hmac_official_sample_in_trade_py() -> None:
    sign = load_trade().sign_access_time_window
    assert (
        sign("hoge", "1721121776490", "1000", "/v1/user/assets")
        == "9ec5745960d05573c8fb047cdd9191bd0c6ede26f07700bb40ecf1a3920abae8"
    )


def test_create_order_requires_live_flag() -> None:
    create_order = load_trade().create_order
    try:
        create_order("k", "s", side="buy", amount=Decimal("0.0001"), price=Decimal("10000000"), live=False)
    except RuntimeError as exc:
        assert "refus" in str(exc).lower()
    else:
        raise AssertionError("create_order must refuse when live=False")


def test_resolve_live_blocked_without_keys() -> None:
    trade = load_trade()
    args = trade.parse_args(["--live"])
    live, key, secret, mode = trade.resolve_live(args, {})
    assert live is False
    assert key == ""
    assert secret == ""
    assert "LIVE_BLOCKED" in mode


def test_resolve_live_on_with_keys() -> None:
    trade = load_trade()
    args = trade.parse_args(["--live"])
    live, key, secret, mode = trade.resolve_live(
        args, {"BITBANK_API_KEY": "k", "BITBANK_API_SECRET": "s"}
    )
    assert live is True
    assert key == "k"
    assert secret == "s"
    assert mode.startswith("LIVE")


def test_synthetic_disables_live_even_with_keys() -> None:
    trade = load_trade()
    args = trade.parse_args(["--live", "--synthetic"])
    live, _key, _secret, mode = trade.resolve_live(
        args, {"BITBANK_API_KEY": "k", "BITBANK_API_SECRET": "s"}
    )
    assert live is False
    assert "SYNTHETIC" in mode


def test_decide_hold_without_candles() -> None:
    trade = load_trade()
    signal, reason = trade.decide([Decimal("1")], False, Decimal("0"), Decimal("0.03"))
    assert signal == "HOLD"
    assert "candle" in reason


def test_size_buy_respects_min_lot() -> None:
    trade = load_trade()
    assert trade.size_buy(Decimal("1000"), Decimal("10000000")) == Decimal("0")
    qty = trade.size_buy(Decimal("10000000"), Decimal("10000000"))
    assert qty >= Decimal("0.0001")
    assert qty == qty.quantize(Decimal("0.0001"))


def test_trade_py_once_synthetic_exits_zero(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("BITBANK_API_KEY", None)
    env.pop("BITBANK_API_SECRET", None)
    env["DRY_RUN"] = "true"
    env["LIVE_TRADING"] = "false"
    env["STATE_PATH"] = str(tmp_path / "state.json")
    env["KILL_SWITCH_PATH"] = str(tmp_path / "KILL")
    proc = subprocess.run(
        [sys.executable, str(TRADE), "--once", "--synthetic", "--dry-run"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "取引画面" in proc.stdout
    assert "BITBANK_API" not in proc.stdout
    assert "create_order" not in proc.stdout.lower()


def test_isolated_trade_py_no_src(tmp_path: Path) -> None:
    dest = tmp_path / "trade.py"
    dest.write_text(TRADE.read_text(encoding="utf-8"), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["DRY_RUN"] = "true"
    env["LIVE_TRADING"] = "false"
    env["STATE_PATH"] = str(tmp_path / "state.json")
    proc = subprocess.run(
        [sys.executable, str(dest), "--once", "--synthetic", "--dry-run"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "取引画面" in proc.stdout


def test_start_sh_live_fallback_is_trade_py() -> None:
    text = ROOT.joinpath("start.sh").read_text(encoding="utf-8")
    assert "trade.py" in text
    assert "python3 trade.py --live" in text or 'trade.py" --live' in text


def test_live_sh_always_has_trade_fallback() -> None:
    text = ROOT.joinpath("live.sh").read_text(encoding="utf-8")
    assert "start_trade" in text
    assert "LIVE_BLOCKED" in text or "keys empty" in text
    assert "exit 2" not in text.split("pick_python")[-1]


def test_live_sh_once_synthetic_starts(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("BITBANK_API_KEY", None)
    env.pop("BITBANK_API_SECRET", None)
    env["STATE_PATH"] = str(tmp_path / "state.json")
    env["KILL_SWITCH_PATH"] = str(tmp_path / "KILL")
    proc = subprocess.run(
        ["bash", str(ROOT / "live.sh"), "--once", "--synthetic"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "取引画面" in proc.stdout
    assert "BITBANK_API" not in proc.stdout
    combined = (proc.stdout + proc.stderr).lower()
    assert "refusing create_order" not in combined
