"""iTerm trading screen. JSON logs stay in logs/bot.log; stdout is this dashboard."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TextIO

from bitbank_bot.money import D, ZERO

JST = timezone(timedelta(hours=9))
CLEAR = "\033[2J\033[H"
WIDTH = 72


def _commas(value: object) -> str:
    try:
        number = D(value)
    except Exception:
        return str(value)
    if number == number.to_integral_value():
        return f"{int(number):,}"
    text = format(number, "f")
    if "." in text:
        whole, frac = text.split(".", 1)
        sign = ""
        if whole.startswith("-"):
            sign = "-"
            whole = whole[1:]
        return f"{sign}{int(whole):,}.{frac}"
    return text


@dataclass
class ScreenView:
    pair: str
    mode: str
    live_orders: bool
    price: str
    public_last: str
    ma: str
    trend: str
    signal_kind: str
    signal_reason: str
    in_position: bool
    position_amount: str
    position_avg: str
    position_tp: str
    watchdog: str
    ws_ok: bool
    cycles: int
    uptime_sec: int
    block_reason: str
    error: str
    candle_type: str
    order_result: str = "SIGNAL_ONLY"
    note: str = "HOLD/待機は正常です。Ctrl-C で停止"


def format_screen(view: ScreenView) -> str:
    mode = "DRY_RUN  実注文なし" if not view.live_orders else "LIVE  実注文オン"
    pos = "なし"
    if view.in_position:
        pos = (
            f"{view.position_amount} BTC  平均 {_commas(view.position_avg)}  "
            f"TP {view.position_tp}"
        )
    ws = "接続" if view.ws_ok else "未接続（RESTで継続）"
    err = view.error or "なし"
    block = view.block_reason or "なし"
    jst = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    bar = "═" * WIDTH
    lines = [
        bar,
        "  Bitbank  BTC/JPY  取引画面",
        f"  {view.pair}   {mode}   稼働中  cycles={view.cycles}  up {view.uptime_sec}s",
        bar,
        f"  公開約定     {_commas(view.public_last)} JPY",
        f"  戦略価格     {_commas(view.price)} JPY    足 {view.candle_type}",
        f"  移動平均     {_commas(view.ma)}    トレンド {view.trend}",
        f"  シグナル     {view.signal_kind}    {view.signal_reason}",
        f"  注文結果     {view.order_result}",
        f"  建玉         {pos}",
        f"  監視         {view.watchdog}    WS {ws}",
        f"  ブロック     {block}",
        f"  エラー       {err}",
        bar,
        f"  {view.note}",
        f"  {jst}",
        "  詳細ログは logs/bot.log（API秘密は出さない）",
        bar,
    ]
    return "\n".join(lines)


class TradingScreen:
    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdout
        self.last_text = ""

    def boot(self, message: str = "取引画面を開いています…") -> str:
        cols = shutil.get_terminal_size((WIDTH, 24)).columns
        bar = "═" * min(WIDTH, max(40, cols))
        text = "\n".join(
            [
                bar,
                "  Bitbank  BTC/JPY  取引画面",
                f"  {message}",
                "  公開APIに接続しています（この画面が取引画面です）",
                "  HOLD/待機は正常です。JSONログではありません。",
                bar,
            ]
        )
        self._write(text)
        self.last_text = text
        return text

    def render(self, view: ScreenView) -> str:
        text = format_screen(view)
        self._write(text)
        self.last_text = text
        return text

    def _write(self, text: str) -> None:
        try:
            self.stream.write(CLEAR + text + "\n")
            self.stream.flush()
        except Exception:
            return


def view_from_engine(
    *,
    pair: str,
    dry_run: bool,
    live_orders: bool,
    price: object,
    public_last: object,
    ma: object,
    trend: str,
    signal_kind: str,
    signal_reason: str,
    in_position: bool,
    position_amount: object = ZERO,
    position_avg: object = ZERO,
    position_tp: object = "",
    watchdog: str,
    ws_ok: bool,
    cycles: int,
    uptime_sec: int,
    block_reason: str = "",
    error: str = "",
    candle_type: str = "1hour",
    order_result: str = "SIGNAL_ONLY",
) -> ScreenView:
    return ScreenView(
        pair=pair,
        mode="DRY_RUN" if dry_run else "LIVE",
        live_orders=live_orders,
        price=str(price),
        public_last=str(public_last if public_last not in (None, "") else price),
        ma=str(ma),
        trend=trend,
        signal_kind=signal_kind,
        signal_reason=signal_reason,
        in_position=in_position,
        position_amount=str(position_amount),
        position_avg=str(position_avg),
        position_tp=str(position_tp),
        watchdog=watchdog or "NORMAL WAIT",
        ws_ok=ws_ok,
        cycles=cycles,
        uptime_sec=uptime_sec,
        block_reason=block_reason,
        error=error,
        candle_type=candle_type,
        order_result=order_result or "SIGNAL_ONLY",
    )


def should_use_screen(args: object, stdout: TextIO | None = None) -> bool:
    stdout = stdout or sys.stdout
    once = bool(getattr(args, "once", False))
    no_screen = bool(getattr(args, "no_screen", False))
    screen = bool(getattr(args, "screen", False))
    max_cycles = getattr(args, "max_cycles", None)
    for flag in ("check_config", "preflight", "backtest"):
        if bool(getattr(args, flag, False)):
            return False
    if no_screen or once:
        return False
    if screen:
        return True
    if max_cycles is not None:
        return False
    return bool(getattr(stdout, "isatty", lambda: False)())
