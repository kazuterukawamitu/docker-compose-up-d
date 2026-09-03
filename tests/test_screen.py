from __future__ import annotations

from io import StringIO

from bitbank_bot.main import build_parser, main
from bitbank_bot.screen import (
    ScreenView,
    TradingScreen,
    format_screen,
    should_use_screen,
    view_from_engine,
)


def test_format_screen_is_trading_dashboard() -> None:
    view = ScreenView(
        pair="btc_jpy",
        mode="DRY_RUN",
        live_orders=False,
        price="10000000",
        public_last="12288796",
        ma="12100000",
        trend="UP",
        signal_kind="HOLD",
        signal_reason="no_buy_setup",
        in_position=False,
        position_amount="0",
        position_avg="0",
        position_tp="",
        watchdog="NORMAL WAIT",
        ws_ok=False,
        cycles=1,
        uptime_sec=3,
        block_reason="",
        error="",
        candle_type="1hour",
    )
    text = format_screen(view)
    assert "取引画面" in text
    assert "btc_jpy" in text
    assert "DRY_RUN" in text
    assert "実注文なし" in text
    assert "HOLD" in text
    assert "12,288,796" in text
    assert "注文結果" in text
    assert "SIGNAL_ONLY" in text


def test_should_use_screen_tty_default() -> None:
    args = build_parser().parse_args([])
    tty = StringIO()
    tty.isatty = lambda: True  # type: ignore[method-assign]
    notty = StringIO()
    notty.isatty = lambda: False  # type: ignore[method-assign]
    assert should_use_screen(args, tty) is True
    assert should_use_screen(args, notty) is False
    args_once = build_parser().parse_args(["--once"])
    assert should_use_screen(args_once, tty) is False
    args_max = build_parser().parse_args(["--max-cycles", "2"])
    assert should_use_screen(args_max, tty) is False
    args_force = build_parser().parse_args(["--screen", "--max-cycles", "2"])
    assert should_use_screen(args_force, notty) is True
    args_off = build_parser().parse_args(["--no-screen"])
    assert should_use_screen(args_off, tty) is False


def test_trading_screen_boot_and_render() -> None:
    buf = StringIO()
    screen = TradingScreen(buf)
    boot = screen.boot("opening")
    assert "取引画面" in boot
    view = view_from_engine(
        pair="btc_jpy",
        dry_run=True,
        live_orders=False,
        price="1",
        public_last="2",
        ma="3",
        trend="DOWN",
        signal_kind="HOLD",
        signal_reason="no_buy_setup",
        in_position=False,
        watchdog="NORMAL WAIT",
        ws_ok=False,
        cycles=0,
        uptime_sec=0,
    )
    text = screen.render(view)
    assert "NORMAL WAIT" in text
    assert "取引画面" in buf.getvalue()


def test_screen_cli_prints_dashboard(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("LOCK_PATH", str(tmp_path / "bot.lock"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("LIVE_TRADING", "false")
    monkeypatch.setenv("ENABLE_WEBSOCKET", "false")
    buf = StringIO()
    monkeypatch.setattr("bitbank_bot.main.sys.stdout", buf)
    rc = main(
        [
            "--screen",
            "--synthetic",
            "--dry-run",
            "--skip-lock",
            "--max-cycles",
            "2",
        ]
    )
    assert rc == 0
    text = buf.getvalue()
    assert "取引画面" in text
    assert "btc_jpy" in text
    assert "HOLD" in text
    assert "create_order" not in text
