from __future__ import annotations

import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import run as stdlib_run  # noqa: E402

from bitbank_bot.strategy import Strategy, build_snapshots  # noqa: E402
from tests.helpers import cfg  # noqa: E402


def test_stdlib_replay_matches_package_buy1() -> None:
    closes = [Decimal(200 - i) for i in range(25)]
    closes.extend([Decimal("176"), Decimal("177")])
    c = cfg(ma_period=3, short_ma_period=3, long_ma_period=5, ma_slope_threshold=Decimal("0.0001"))
    snaps = build_snapshots(closes, list(range(len(closes))), c)
    strat = Strategy(c)
    package = [strat.evaluate(snap, None).kind for snap in snaps]
    standalone = [
        kind
        for kind, _reason, _tp in stdlib_run.replay_signals(
            closes,
            list(range(len(closes))),
            ma_period=3,
            short_period=3,
            long_period=5,
            slope=Decimal("0.0001"),
        )
    ]
    assert package == standalone
    assert "BUY1" in standalone


def test_stdlib_replay_matches_package_sell3() -> None:
    closes = [Decimal(200 - i) for i in range(30)] + [Decimal("168"), Decimal("172")]
    c = cfg(
        ma_period=5,
        short_ma_period=5,
        long_ma_period=8,
        ma_slope_threshold=Decimal("0.0001"),
    )
    snaps = build_snapshots(closes, list(range(len(closes))), c)
    from bitbank_bot.strategy import Position

    pos = Position(
        amount=Decimal("0.01"),
        average_price=Decimal("180"),
        tp_pct=Decimal("0.03"),
        entry_candle_index=0,
        entry_candle_ts=0,
        actual_execution_jpy=Decimal("1800"),
        kind="BUY4",
    )
    strat = Strategy(c)
    package = [
        strat.evaluate(snap, pos if snap.index != 0 else None).kind for snap in snaps
    ]
    standalone = [
        kind
        for kind, _reason, _tp in stdlib_run.replay_signals(
            closes,
            list(range(len(closes))),
            active_from_index=1,
            entry=Decimal("180"),
            tp=Decimal("0.03"),
            entry_index=0,
            ma_period=5,
            short_period=5,
            long_period=8,
            slope=Decimal("0.0001"),
        )
    ]
    assert package == standalone
    assert "SELL3" in standalone


def test_run_py_compiles() -> None:
    path = Path(__file__).resolve().parents[1] / "run.py"
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")
    assert "create_order(" not in source
    assert "/user/spot/order" not in source
    assert "urllib.request" in source


def test_run_py_once_synthetic_no_deps(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [sys.executable, str(root / "run.py"), "--once", "--synthetic", "--no-screen"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "取引画面" in proc.stdout
    assert "DRY_RUN" in proc.stdout
    assert "run complete" in proc.stdout


def test_run_py_works_without_repo_src(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    copied = tmp_path / "run.py"
    copied.write_text((root / "run.py").read_text(encoding="utf-8"), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [sys.executable, str(copied), "--once", "--synthetic", "--no-screen"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "Bitbank  BTC/JPY  取引画面" in proc.stdout


def test_start_sh_falls_back_to_run_py() -> None:
    text = Path(__file__).resolve().parents[1].joinpath("start.sh").read_text(encoding="utf-8")
    assert "run.py" in text
    assert "stdlib DRY_RUN" in text
