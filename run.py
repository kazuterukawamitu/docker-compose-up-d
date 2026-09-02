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
SLOPE = Decimal("0.0005")
BUY1_TP = Decimal("0.03")
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


def decide(
    closes: list[Decimal],
    in_position: bool,
    entry: Decimal,
    tp: Decimal,
) -> tuple[str, str]:
    if len(closes) < MA_PERIOD + 1:
        return "HOLD", "not_enough_candles"
    ma = sma(closes, MA_PERIOD)
    prev_ma = sma(closes[:-1], MA_PERIOD)
    if ma is None or prev_ma is None:
        return "HOLD", "not_enough_candles"
    close = closes[-1]
    prev_close = closes[-2]
    prev_trend = trend_of(prev_ma, sma(closes[:-2], MA_PERIOD) or prev_ma)
    trend = trend_of(ma, prev_ma)
    crossed_up = prev_close <= prev_ma and close > ma
    crossed_down = prev_close >= prev_ma and close < ma
    if in_position:
        target = entry * (Decimal("1") + tp)
        if close >= target:
            return "TP", f"take_profit {commas(close)} >= {commas(target)}"
        if trend == "DOWN" and crossed_up:
            return "SELL3", "downtrend_ma_cross_up"
        if crossed_down and close < prev_close:
            return "SELL2", "cross_down_and_falling"
        return "HOLD", "in_position_no_sell_or_tp"
    if prev_trend == "DOWN" and trend in {"FLAT", "UP"} and crossed_up:
        return "BUY1", "ma_left_downtrend_cross_up"
    if trend == "UP" and crossed_down:
        return "BUY2", "uptrend_cross_down"
    return "HOLD", "no_buy_setup"


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
    amount = Decimal("0")
    tp = BUY1_TP
    last_error = ""
    print("Bitbank BTC/JPY DRY_RUN を起動します（実注文なし / pip不要）", flush=True)
    while True:
        try:
            rows = synthetic_closes() if args.synthetic else fetch_hourly_closes()
            closes = [c for _, c in rows]
            ticker = {"last": str(closes[-1]) if closes else ""}
            if not args.synthetic:
                ticker = fetch_ticker()
            ma = sma(closes, MA_PERIOD)
            prev_ma = sma(closes[:-1], MA_PERIOD) if len(closes) > MA_PERIOD else None
            trend = trend_of(ma, prev_ma) if ma is not None and prev_ma is not None else "-"
            signal, reason = decide(closes, in_position, entry, tp)
            last = ticker.get("last") or (str(closes[-1]) if closes else "-")
            if signal == "BUY1" or signal == "BUY2":
                price = D(last)
                if price > 0:
                    raw = (PAPER_JPY * Decimal("0.95")) / price
                    amount = (raw // MIN_BTC) * MIN_BTC
                    if amount >= MIN_BTC:
                        in_position = True
                        entry = price
                        tp = BUY1_TP
                        print(
                            f"ORDER_INTENT paper {signal} {amount} BTC @ {commas(price)} "
                            "(DRY_RUN: Bitbank create_order は呼ばない)",
                            flush=True,
                        )
            elif signal in {"SELL2", "SELL3", "TP"} and in_position:
                print(
                    f"ORDER_INTENT paper {signal} flatten {amount} BTC "
                    "(DRY_RUN: Bitbank create_order は呼ばない)",
                    flush=True,
                )
                in_position = False
                amount = Decimal("0")
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
