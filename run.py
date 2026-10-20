#!/usr/bin/env python3
"""Bitbank BTC/JPY DRY_RUN bot — standard library only.

This file is the program that must run on a Mac with only python3.
It never places orders. It never needs pip, venv, httpx, or dotenv.

    python3 run.py

Stop with Ctrl-C.
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

PAIR = "btc_jpy"
PUBLIC = "https://public.bitbank.cc"
MA_PERIOD = 20
LONG_PERIOD = 50
SLOPE = Decimal("0.0005")
BUY1_TP = Decimal("0.03")
BUY2_TP = Decimal("0.05")
BUY2_GOLDEN_TP = Decimal("0.08")
BUY3_TP = Decimal("0.04")
BUY4_TP = Decimal("0.05")
BUY3_EXTEND = Decimal("0.05")
BUY4_DIP = Decimal("0.05")
SELL1_EXTEND = Decimal("0.04")
SELL4_DIP = Decimal("0.04")
MIN_BTC = Decimal("0.0001")
PAPER_JPY = Decimal("100000")
POLL_SEC = 5
LONG_WAIT_SEC = 900
JST = timezone(timedelta(hours=9))
HOUR_MS = 3_600_000
CLEAR = "\033[2J\033[H"

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def D(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidOperation(f"number expected: {value!r}") from exc


def commas(value: object) -> str:
    try:
        number = D(value)
    except Exception:
        return str(value)
    if number == number.to_integral_value():
        return f"{int(number):,}"
    text = format(number, "f")
    if "." in text:
        whole, frac = text.split(".", 1)
        return f"{int(whole):,}.{frac}"
    return text


def http_get_json(url: str, timeout: float = 15.0) -> dict[str, Any]:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "bitbank-btc-jpy-dry-run"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        raw = resp.read().decode("utf-8")
    payload = json.loads(raw)
    if payload.get("success") != 1:
        raise RuntimeError(f"bitbank success!=1 url={url}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("bitbank data missing")
    return data


def fetch_ticker() -> dict[str, str]:
    data = http_get_json(f"{PUBLIC}/{PAIR}/ticker")
    return {
        "last": str(data.get("last") or ""),
        "buy": str(data.get("buy") or ""),
        "sell": str(data.get("sell") or ""),
    }


def fetch_hourly_closes(days: int = 4) -> list[tuple[int, Decimal]]:
    now = datetime.now(JST)
    seen: set[int] = set()
    rows: list[tuple[int, Decimal]] = []
    for i in range(days):
        key = (now - timedelta(days=i)).strftime("%Y%m%d")
        try:
            data = http_get_json(f"{PUBLIC}/{PAIR}/candlestick/1hour/{key}")
        except Exception:
            continue
        sticks = data.get("candlestick") or []
        if not sticks:
            continue
        for row in sticks[0].get("ohlcv") or []:
            if not isinstance(row, list) or len(row) < 6:
                continue
            ts = int(row[5])
            if ts in seen:
                continue
            seen.add(ts)
            rows.append((ts, D(row[3])))
    rows.sort(key=lambda item: item[0])
    now_ms = int(now.timestamp() * 1000)
    if rows and now_ms < rows[-1][0] + HOUR_MS:
        rows = rows[:-1]
    return rows


def synthetic_closes(n: int = 80) -> list[tuple[int, Decimal]]:
    now_ms = int(datetime.now(JST).timestamp() * 1000)
    last = now_ms - (now_ms % HOUR_MS) - HOUR_MS
    base = last - (n - 1) * HOUR_MS
    out: list[tuple[int, Decimal]] = []
    price = Decimal("10000000")
    for i in range(n):
        out.append((base + i * HOUR_MS, price - Decimal(i) * Decimal("5000")))
    return out


def sma(values: list[Decimal], period: int) -> Decimal | None:
    if len(values) < period:
        return None
    return sum(values[-period:], Decimal("0")) / Decimal(period)


def trend_of(ma: Decimal, prev: Decimal) -> str:
    if prev == 0:
        return "FLAT"
    slope = (ma - prev) / prev
    if slope > SLOPE:
        return "UP"
    if slope < -SLOPE:
        return "DOWN"
    return "FLAT"


def series_sma(values: list[Decimal], period: int) -> list[Decimal | None]:
    out: list[Decimal | None] = [None] * len(values)
    if period < 1:
        return out
    running = Decimal("0")
    for i, value in enumerate(values):
        running += value
        if i >= period:
            running -= values[i - period]
        if i + 1 >= period:
            out[i] = running / Decimal(period)
    return out


class _Buy3:
    def __init__(self, extend: Decimal) -> None:
        self.extend = extend
        self.phase = "idle"
        self.peak: Decimal | None = None
        self.trough: Decimal | None = None
        self.prev: Decimal | None = None

    def reset(self) -> None:
        self.phase = "idle"
        self.peak = None
        self.trough = None

    def update(self, close: Decimal, ma: Decimal) -> bool:
        fired = False
        if close <= ma:
            self.reset()
            self.prev = close
            return False
        threshold = ma * (Decimal("1") + self.extend)
        if self.phase == "idle":
            if close >= threshold:
                self.phase = "extended"
                self.peak = close
        elif self.phase == "extended":
            if self.peak is None or close > self.peak:
                self.peak = close
            elif self.prev is not None and close < self.prev:
                self.phase = "pullback"
                self.trough = close
        elif self.phase == "pullback":
            if self.trough is None or close < self.trough:
                self.trough = close
            if self.prev is not None and close > self.prev:
                fired = True
                self.reset()
        self.prev = close
        return fired


class _Buy4:
    def __init__(self, dip: Decimal) -> None:
        self.dip = dip
        self.phase = "idle"
        self.prev: Decimal | None = None
        self.low: Decimal | None = None

    def update(self, close: Decimal, ma: Decimal, trend: str) -> bool:
        fired = False
        if trend != "DOWN":
            self.phase = "idle"
            self.low = None
            self.prev = close
            return False
        floor = ma * (Decimal("1") - self.dip)
        if self.phase == "idle":
            if close <= floor:
                self.phase = "dipped"
                self.low = close
        elif self.phase == "dipped":
            if self.low is None or close < self.low:
                self.low = close
            if self.prev is not None and close > self.prev:
                fired = True
                self.phase = "idle"
                self.low = None
        self.prev = close
        return fired


class _Sell1:
    def __init__(self, extend: Decimal) -> None:
        self.extend = extend
        self.phase = "idle"
        self.prev: Decimal | None = None
        self.pivot: Decimal | None = None

    def update(self, close: Decimal, ma: Decimal) -> bool:
        fired = False
        ceiling = ma * (Decimal("1") + self.extend)
        if self.phase == "idle":
            if close >= ceiling:
                self.phase = "extended"
                self.pivot = close
        elif self.phase == "extended":
            if self.pivot is None or close > self.pivot:
                self.pivot = close
            if self.prev is not None and close < self.prev:
                fired = True
                self.phase = "idle"
            elif close < ma:
                self.phase = "idle"
                self.pivot = None
        self.prev = close
        return fired


class _Sell2:
    def __init__(self) -> None:
        self.phase = "idle"

    def update(self, close: Decimal, prev_close: Decimal, crossed_dn: bool) -> bool:
        fired = False
        falling = close < prev_close
        if self.phase == "idle":
            if falling:
                self.phase = "crossed" if crossed_dn else "falling"
        elif self.phase == "falling":
            if crossed_dn and falling:
                self.phase = "crossed"
            elif not falling:
                self.phase = "idle"
        elif self.phase == "crossed":
            if falling:
                fired = True
            self.phase = "idle"
        return fired


class _Sell4:
    def __init__(self, dip: Decimal) -> None:
        self.dip = dip
        self.phase = "idle"
        self.peak: Decimal | None = None
        self.prev: Decimal | None = None

    def update(self, close: Decimal, ma: Decimal) -> bool:
        fired = False
        floor = ma * (Decimal("1") - self.dip)
        if close >= ma:
            self.phase = "idle"
            self.peak = None
            self.prev = close
            return False
        if self.phase == "idle":
            if close <= floor:
                self.phase = "dipped"
        elif self.phase == "dipped":
            if self.prev is not None and close > self.prev:
                self.phase = "recovery"
                self.peak = close
        elif self.phase == "recovery":
            if self.peak is None or close > self.peak:
                self.peak = close
            elif self.prev is not None and close < self.prev:
                fired = True
                self.phase = "idle"
                self.peak = None
        self.prev = close
        return fired


def replay_signals(
    closes: list[Decimal],
    timestamps: list[int],
    *,
    active_from_index: int | None = None,
    entry: Decimal = Decimal("0"),
    tp: Decimal = BUY1_TP,
    entry_index: int = -1,
    entry_ts: int = 0,
    ma_period: int = MA_PERIOD,
    short_period: int = MA_PERIOD,
    long_period: int = LONG_PERIOD,
    slope: Decimal = SLOPE,
    buy1_tp: Decimal = BUY1_TP,
    buy2_tp: Decimal = BUY2_TP,
    buy2_golden_tp: Decimal = BUY2_GOLDEN_TP,
    buy3_tp: Decimal = BUY3_TP,
    buy4_tp: Decimal = BUY4_TP,
    buy3_extend: Decimal = BUY3_EXTEND,
    buy4_dip: Decimal = BUY4_DIP,
    sell1_extend: Decimal = SELL1_EXTEND,
    sell4_dip: Decimal = SELL4_DIP,
) -> list[tuple[str, str, Decimal]]:
    """Replay README rules. Same priority as the package: SELL, then TP, then BUY."""
    primary = series_sma(closes, ma_period)
    short = series_sma(closes, short_period)
    long = series_sma(closes, long_period)
    buy3 = _Buy3(buy3_extend)
    buy4 = _Buy4(buy4_dip)
    sell1 = _Sell1(sell1_extend)
    sell2 = _Sell2()
    sell4 = _Sell4(sell4_dip)
    out: list[tuple[str, str, Decimal]] = []
    prev_trend = "FLAT"
    start = max(ma_period, short_period, long_period)
    for i in range(start, len(closes)):
        ma = primary[i]
        prev_ma = primary[i - 1]
        s_ma = short[i]
        s_prev = short[i - 1]
        l_ma = long[i]
        l_prev = long[i - 1]
        if None in (ma, prev_ma, s_ma, s_prev, l_ma, l_prev):
            continue
        assert ma is not None and prev_ma is not None
        assert s_ma is not None and s_prev is not None
        assert l_ma is not None and l_prev is not None
        if prev_ma == 0:
            trend = "FLAT"
        else:
            delta = (ma - prev_ma) / prev_ma
            if delta > slope:
                trend = "UP"
            elif delta < -slope:
                trend = "DOWN"
            else:
                trend = "FLAT"
        close = closes[i]
        prev_close = closes[i - 1]
        up = prev_close <= prev_ma and close > ma
        down = prev_close >= prev_ma and close < ma
        golden = s_prev <= l_prev and s_ma > l_ma
        b3 = buy3.update(close, ma)
        b4 = buy4.update(close, ma, trend)
        s1 = sell1.update(close, ma)
        s2 = sell2.update(close, prev_close, down)
        s4 = sell4.update(close, ma)
        in_position = active_from_index is not None and i >= active_from_index
        bar_ts = timestamps[i] if i < len(timestamps) else 0
        same_entry = i == entry_index or (entry_ts > 0 and bar_ts == entry_ts)
        if in_position and same_entry:
            out.append(("HOLD", "same_entry_candle_no_sell", tp))
        elif in_position:
            if s1:
                out.append(("SELL1", "price >=4% above MA then turned down", tp))
            elif trend == "DOWN" and up:
                out.append(("SELL3", "downtrend_ma_cross_up", tp))
            elif s2:
                out.append(("SELL2", "cross_down_and_falling", tp))
            elif s4:
                out.append(("SELL4", "failed recovery below MA", tp))
            elif close >= entry * (Decimal("1") + tp):
                out.append(("TP", "take_profit", tp))
            else:
                out.append(("HOLD", "in_position_no_sell_or_tp", tp))
        elif prev_trend == "DOWN" and trend in {"FLAT", "UP"} and up:
            out.append(("BUY1", "ma_left_downtrend_cross_up", buy1_tp))
        elif trend == "UP" and down:
            chosen = buy2_golden_tp if golden else buy2_tp
            out.append(("BUY2", "uptrend_cross_down", chosen))
        elif b3:
            out.append(("BUY3", "pullback then bounce above MA", buy3_tp))
        elif b4:
            out.append(("BUY4", "downtrend dip then rise", buy4_tp))
        else:
            out.append(("HOLD", "no_buy_setup", tp))
        prev_trend = trend
    return out


def latest_signal(
    closes: list[Decimal],
    timestamps: list[int],
    *,
    in_position: bool,
    entry: Decimal,
    tp: Decimal,
    entry_ts: int,
) -> tuple[str, str, Decimal]:
    if len(closes) < MA_PERIOD + 1:
        return "HOLD", "not_enough_candles", tp
    entry_index = -1
    active_from: int | None = None
    if in_position:
        for i, ts in enumerate(timestamps):
            if ts == entry_ts:
                entry_index = i
                break
        active_from = entry_index if entry_index >= 0 else 0
    rows = replay_signals(
        closes,
        timestamps,
        active_from_index=active_from,
        entry=entry,
        tp=tp,
        entry_index=entry_index,
        entry_ts=entry_ts if in_position else 0,
    )
    if not rows:
        return "HOLD", "not_enough_candles", tp
    return rows[-1]


def screen(
    *,
    last: str,
    ma: str,
    trend: str,
    signal: str,
    reason: str,
    cycles: int,
    uptime: int,
    watchdog: str,
    error: str,
    in_position: bool,
    amount: Decimal,
    entry: Decimal,
) -> str:
    pos = "なし"
    if in_position:
        pos = f"{amount} BTC  平均 {commas(entry)}"
    bar = "═" * 72
    jst = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    return "\n".join(
        [
            bar,
            "  Bitbank  BTC/JPY  取引画面",
            f"  btc_jpy   DRY_RUN  実注文なし   稼働中  cycles={cycles}  up {uptime}s",
            bar,
            f"  公開約定     {commas(last)} JPY",
            f"  移動平均     {commas(ma)}    トレンド {trend}",
            f"  シグナル     {signal}    {reason}",
            f"  建玉         {pos}",
            f"  監視         {watchdog}",
            f"  エラー       {error or 'なし'}",
            bar,
            "  HOLD/待機は正常です。このプログラムは注文しません。Ctrl-C で停止",
            f"  {jst}",
            bar,
        ]
    )


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bitbank BTC/JPY DRY_RUN (stdlib, no orders)")
    p.add_argument("--once", action="store_true")
    p.add_argument("--synthetic", action="store_true")
    p.add_argument("--max-cycles", type=int, default=None)
    p.add_argument("--screen", action="store_true")
    p.add_argument("--no-screen", action="store_true")
    p.add_argument("--skip-lock", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    use_screen = not args.no_screen and not args.once
    started = time.monotonic()
    cycles = 0
    in_position = False
    entry = Decimal("0")
    entry_ts = 0
    amount = Decimal("0")
    tp = BUY1_TP
    last_error = ""
    print("Bitbank BTC/JPY DRY_RUN を起動します（実注文なし / pip不要）", flush=True)
    while True:
        try:
            rows = synthetic_closes() if args.synthetic else fetch_hourly_closes()
            closes = [c for _, c in rows]
            stamps = [ts for ts, _ in rows]
            ticker = {"last": str(closes[-1]) if closes else ""}
            if not args.synthetic:
                ticker = fetch_ticker()
            ma = sma(closes, MA_PERIOD)
            prev_ma = sma(closes[:-1], MA_PERIOD) if len(closes) > MA_PERIOD else None
            trend = trend_of(ma, prev_ma) if ma is not None and prev_ma is not None else "-"
            signal, reason, signal_tp = latest_signal(
                closes,
                stamps,
                in_position=in_position,
                entry=entry,
                tp=tp,
                entry_ts=entry_ts,
            )
            last = ticker.get("last") or (str(closes[-1]) if closes else "-")
            if signal in {"BUY1", "BUY2", "BUY3", "BUY4"}:
                price = D(last)
                if price > 0:
                    raw = (PAPER_JPY * Decimal("0.95")) / price
                    amount = (raw // MIN_BTC) * MIN_BTC
                    if amount >= MIN_BTC:
                        in_position = True
                        entry = price
                        entry_ts = stamps[-1] if stamps else 0
                        tp = signal_tp
                        print(
                            f"ORDER_INTENT paper {signal} {amount} BTC @ {commas(price)} "
                            "(DRY_RUN: Bitbank create_order は呼ばない)",
                            flush=True,
                        )
            elif signal in {"SELL1", "SELL2", "SELL3", "SELL4", "TP"} and in_position:
                print(
                    f"ORDER_INTENT paper {signal} flatten {amount} BTC "
                    "(DRY_RUN: Bitbank create_order は呼ばない)",
                    flush=True,
                )
                in_position = False
                amount = Decimal("0")
                entry_ts = 0
            uptime = int(time.monotonic() - started)
            watchdog = "LONG_WAIT" if uptime >= LONG_WAIT_SEC else "NORMAL WAIT"
            text = screen(
                last=last,
                ma=str(ma) if ma is not None else "-",
                trend=trend,
                signal=signal,
                reason=reason,
                cycles=cycles,
                uptime=uptime,
                watchdog=watchdog,
                error=last_error,
                in_position=in_position,
                amount=amount,
                entry=entry,
            )
            if use_screen:
                sys.stdout.write(CLEAR + text + "\n")
            else:
                sys.stdout.write(text + "\n")
            sys.stdout.flush()
            last_error = ""
            cycles += 1
            if args.once or (args.max_cycles is not None and cycles >= args.max_cycles):
                print("run complete", flush=True)
                return 0
            time.sleep(POLL_SEC)
        except KeyboardInterrupt:
            print("\nstopped", flush=True)
            return 0
        except Exception as exc:
            last_error = type(exc).__name__
            print(f"loop error {last_error}: {exc}", flush=True)
            cycles += 1
            if args.once or (args.max_cycles is not None and cycles >= args.max_cycles):
                return 2
            time.sleep(POLL_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
