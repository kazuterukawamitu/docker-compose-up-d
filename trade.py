#!/usr/bin/env python3
"""Bitbank BTC/JPY automated trader — standard library only.

Always starts a 取引画面. Places real Bitbank orders only when --live
is set and .env has API keys (or DRY_RUN=false and LIVE_TRADING=true).

    python3 trade.py --live

No pip, venv, or httpx required. Ctrl-C stops.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

PAIR = "btc_jpy"
PUBLIC = "https://public.bitbank.cc"
PRIVATE = "https://api.bitbank.cc/v1"
MA_PERIOD = 20
SLOPE = Decimal("0.0005")
BUY1_TP = Decimal("0.03")
MIN_BTC = Decimal("0.0001")
USAGE = Decimal("0.95")
FEE = Decimal("0.0015")
PAPER_JPY = Decimal("100000")
POLL_SEC = 5
LONG_WAIT_SEC = 900
WINDOW_MS = "5000"
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
    return Decimal(str(value))


def commas(value: object) -> str:
    try:
        number = D(value)
    except (InvalidOperation, ValueError):
        return str(value)
    if number == number.to_integral_value():
        return f"{int(number):,}"
    text = format(number, "f")
    if "." in text:
        whole, frac = text.split(".", 1)
        return f"{int(whole):,}.{frac}"
    return text


def load_dotenv() -> dict[str, str]:
    env: dict[str, str] = {}
    here = Path(__file__).resolve().parent
    cwd = Path.cwd()
    candidates = [
        cwd / ".env",
        here / ".env",
        Path.home() / "docker-compose-up-d" / ".env",
        Path.home() / "bitbank.env",
    ]
    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def sign_access_time_window(secret: str, request_time: str, window: str, payload: str) -> str:
    message = f"{request_time}{window}{payload}"
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def redact(message: str, *secrets: str) -> str:
    text = str(message)
    for secret in secrets:
        if secret and secret in text:
            text = text.replace(secret, "[redacted]")
    return text


def kill_switch_on() -> bool:
    return Path(os.environ.get("KILL_SWITCH_PATH", "data/KILL")).exists()


def state_path() -> Path:
    return Path(os.environ.get("STATE_PATH", "data/trade_state.json"))


def load_state() -> dict[str, Any]:
    path = state_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def save_state(state: dict[str, Any]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def http_json(
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    hdrs = {"User-Agent": "bitbank-btc-jpy-trade", "Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST" if data else "GET")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as err:
            raise RuntimeError(f"http {exc.code}") from err
    else:
        payload = json.loads(raw)
    if payload.get("success") != 1:
        data_obj = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        code = data_obj.get("code") if isinstance(data_obj, dict) else None
        raise RuntimeError(f"bitbank success!=1 code={code}")
    data_obj = payload.get("data")
    if not isinstance(data_obj, dict):
        raise RuntimeError("bitbank data missing")
    return data_obj


def public_get(path: str) -> dict[str, Any]:
    return http_json(PUBLIC + path)


def private_headers(secret: str, key: str, payload: str) -> dict[str, str]:
    request_time = str(int(time.time() * 1000))
    signature = sign_access_time_window(secret, request_time, WINDOW_MS, payload)
    return {
        "ACCESS-KEY": key,
        "ACCESS-REQUEST-TIME": request_time,
        "ACCESS-TIME-WINDOW": WINDOW_MS,
        "ACCESS-SIGNATURE": signature,
    }


def private_get(key: str, secret: str, path: str, query: dict[str, str] | None = None) -> dict[str, Any]:
    if not path.startswith("/"):
        path = "/" + path
    sign_path = "/v1" + path
    qs = ""
    if query:
        qs = "?" + urllib.parse.urlencode(query)
        sign_path += qs
    url = PRIVATE + path + qs
    return http_json(url, headers=private_headers(secret, key, sign_path))


def private_post(key: str, secret: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    if not path.startswith("/"):
        path = "/" + path
    raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    url = PRIVATE + path
    return http_json(url, data=raw.encode("utf-8"), headers=private_headers(secret, key, raw))


def fetch_ticker() -> dict[str, str]:
    data = public_get(f"/{PAIR}/ticker")
    return {"last": str(data.get("last") or ""), "buy": str(data.get("buy") or ""), "sell": str(data.get("sell") or "")}


def fetch_hourly_closes(days: int = 4) -> list[tuple[int, Decimal]]:
    now = datetime.now(JST)
    seen: set[int] = set()
    rows: list[tuple[int, Decimal]] = []
    for i in range(days):
        key = (now - timedelta(days=i)).strftime("%Y%m%d")
        try:
            data = public_get(f"/{PAIR}/candlestick/1hour/{key}")
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
        if entry > 0:
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


def free_amounts(key: str, secret: str) -> tuple[Decimal, Decimal]:
    data = private_get(key, secret, "/user/assets")
    jpy = Decimal("0")
    btc = Decimal("0")
    for row in data.get("assets") or []:
        if row.get("asset") == "jpy":
            jpy = D(row.get("free_amount"))
        elif row.get("asset") == "btc":
            btc = D(row.get("free_amount"))
    return jpy, btc


def active_count(key: str, secret: str) -> int:
    data = private_get(key, secret, "/user/spot/active_orders", {"pair": PAIR})
    return len(data.get("orders") or [])


def create_order(
    key: str,
    secret: str,
    *,
    side: str,
    amount: Decimal,
    price: Decimal,
    live: bool,
) -> dict[str, Any]:
    if not live:
        raise RuntimeError("refusing create_order unless live")
    qty = amount.quantize(MIN_BTC)
    if qty < MIN_BTC or price <= 0:
        raise RuntimeError("invalid amount/price")
    body = {
        "pair": PAIR,
        "amount": format(qty, "f"),
        "side": side,
        "type": "limit",
        "price": str(int(price.to_integral_value())),
    }
    return private_post(key, secret, "/user/spot/order", body)


def size_buy(jpy: Decimal, price: Decimal) -> Decimal:
    if price <= 0:
        return Decimal("0")
    raw = jpy * USAGE * (Decimal("1") - FEE) / price
    amt = (raw // MIN_BTC) * MIN_BTC
    return amt if amt >= MIN_BTC else Decimal("0")


def size_sell(btc: Decimal) -> Decimal:
    amt = (btc // MIN_BTC) * MIN_BTC
    return amt if amt >= MIN_BTC else Decimal("0")


def screen(
    *,
    mode: str,
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
    note: str,
) -> str:
    pos = "なし"
    if in_position:
        pos = f"{amount} BTC  平均 {commas(entry)}"
    bar = "═" * 72
    jst = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    return "\n".join(
        [
            bar,
            "  Bitbank  BTC/JPY  自動売買  取引画面",
            f"  btc_jpy   {mode}   稼働中  cycles={cycles}  up {uptime}s",
            bar,
            f"  公開約定     {commas(last)} JPY",
            f"  移動平均     {commas(ma)}    トレンド {trend}",
            f"  シグナル     {signal}    {reason}",
            f"  建玉         {pos}",
            f"  監視         {watchdog}",
            f"  エラー       {error or 'なし'}",
            bar,
            f"  {note}",
            f"  {jst}",
            bar,
        ]
    )


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bitbank BTC/JPY trader (stdlib)")
    p.add_argument("--live", action="store_true", help="place real orders when keys are in .env")
    p.add_argument("--once", action="store_true")
    p.add_argument("--synthetic", action="store_true")
    p.add_argument("--max-cycles", type=int, default=None)
    p.add_argument("--screen", action="store_true")
    p.add_argument("--no-screen", action="store_true")
    p.add_argument("--skip-lock", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--require-live", action="store_true")
    p.add_argument("--check-config", action="store_true")
    return p.parse_args(argv)


def resolve_live(args: argparse.Namespace, file_env: dict[str, str]) -> tuple[bool, str, str, str]:
    key = file_env.get("BITBANK_API_KEY") or os.environ.get("BITBANK_API_KEY") or ""
    secret = file_env.get("BITBANK_API_SECRET") or os.environ.get("BITBANK_API_SECRET") or ""
    dry = truthy(file_env.get("DRY_RUN", os.environ.get("DRY_RUN", "true")))
    live_flag = truthy(file_env.get("LIVE_TRADING", os.environ.get("LIVE_TRADING", "false")))
    if args.dry_run:
        return False, key, secret, "DRY_RUN  実注文なし"
    if args.synthetic:
        return False, key, secret, "SYNTHETIC  実注文なし"
    want = bool(args.live or args.require_live or (live_flag and not dry))
    if not want:
        return False, key, secret, "DRY_RUN  実注文なし"
    if not key or not secret:
        return False, key, secret, "LIVE_BLOCKED  .envにAPIキーを入れて再起動"
    return True, key, secret, "LIVE  実注文オン"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    file_env = load_dotenv()
    live, api_key, api_secret, mode = resolve_live(args, file_env)
    if args.check_config:
        print(f"mode={mode}")
        print(f"may_place_live_orders={str(live).lower()}")
        print(f"has_api_key={str(bool(api_key)).lower()}")
        print(f"pair={PAIR}")
        if args.require_live and not live:
            return 2
        return 0
    use_screen = not args.no_screen and not args.once
    started = time.monotonic()
    cycles = 0
    saved = load_state()
    in_position = bool(saved.get("in_position"))
    entry = D(saved.get("entry") or 0)
    amount = D(saved.get("amount") or 0)
    tp = BUY1_TP
    last_error = ""
    last_order = str(saved.get("last_order") or "")
    print(f"Bitbank BTC/JPY 自動売買を起動します ({mode})", flush=True)
    if live:
        print("LIVE: READMEシグナルで POST /v1/user/spot/order します。Ctrl-C で停止。", flush=True)
    else:
        print("注文は出しません。実売買は: python3 trade.py --live （.env にキー）", flush=True)
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
            last = ticker.get("last") or (str(closes[-1]) if closes else "-")
            price = D(last) if last not in {"", "-"} else Decimal("0")
            ask = D(ticker.get("sell") or 0) or price
            bid = D(ticker.get("buy") or 0) or price

            if live:
                jpy, btc = free_amounts(api_key, api_secret)
                if btc >= MIN_BTC:
                    in_position = True
                    amount = size_sell(btc) or btc
                else:
                    in_position = False
                    amount = Decimal("0")

            signal, reason = decide(closes, in_position, entry, tp)
            blocked = kill_switch_on()
            if blocked and signal in {"BUY1", "BUY2", "SELL2", "SELL3", "TP"}:
                last_error = "KILL"
            elif signal in {"BUY1", "BUY2"} and price > 0 and not in_position:
                if live:
                    jpy, btc = free_amounts(api_key, api_secret)
                    qty = size_buy(jpy, ask or price)
                    pending = active_count(api_key, api_secret)
                    if qty >= MIN_BTC and pending == 0:
                        raw = create_order(
                            api_key,
                            api_secret,
                            side="buy",
                            amount=qty,
                            price=ask or price,
                            live=True,
                        )
                        last_order = f"LIVE BUY {raw.get('order_id')} {qty}"
                        in_position = True
                        amount = qty
                        entry = ask or price
                        save_state(
                            {
                                "in_position": True,
                                "entry": str(entry),
                                "amount": str(amount),
                                "last_order": last_order,
                            }
                        )
                        print(last_order, flush=True)
                    else:
                        last_error = f"buy_blocked qty={qty} pending={pending}"
                else:
                    qty = size_buy(PAPER_JPY, price)
                    if qty >= MIN_BTC:
                        in_position = True
                        amount = qty
                        entry = price
                        save_state(
                            {
                                "in_position": True,
                                "entry": str(entry),
                                "amount": str(amount),
                                "last_order": f"paper {signal}",
                            }
                        )
                        print(f"ORDER_INTENT paper {signal} {qty} BTC (no create_order)", flush=True)
            elif signal in {"SELL2", "SELL3", "TP"} and in_position:
                if live:
                    _jpy, btc = free_amounts(api_key, api_secret)
                    qty = size_sell(btc)
                    pending = active_count(api_key, api_secret)
                    if qty >= MIN_BTC and pending == 0:
                        raw = create_order(
                            api_key,
                            api_secret,
                            side="sell",
                            amount=qty,
                            price=bid or price,
                            live=True,
                        )
                        last_order = f"LIVE SELL {raw.get('order_id')} {qty}"
                        in_position = False
                        amount = Decimal("0")
                        save_state(
                            {
                                "in_position": False,
                                "entry": "0",
                                "amount": "0",
                                "last_order": last_order,
                            }
                        )
                        print(last_order, flush=True)
                    else:
                        last_error = f"sell_blocked qty={qty} pending={pending}"
                else:
                    print(f"ORDER_INTENT paper {signal} flatten (no create_order)", flush=True)
                    in_position = False
                    amount = Decimal("0")
                    save_state(
                        {
                            "in_position": False,
                            "entry": "0",
                            "amount": "0",
                            "last_order": f"paper {signal}",
                        }
                    )

            uptime = int(time.monotonic() - started)
            watchdog = "LONG_WAIT" if uptime >= LONG_WAIT_SEC else "NORMAL WAIT"
            note = "HOLD/待機は正常です。Ctrl-C で停止"
            if last_order:
                note = last_order
            text = screen(
                mode=mode,
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
                note=note,
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
            print(
                f"loop error {last_error}: {redact(str(exc), api_key, api_secret)}",
                file=sys.stderr,
                flush=True,
            )
            cycles += 1
            if args.once or (args.max_cycles is not None and cycles >= args.max_cycles):
                return 2
            time.sleep(POLL_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
