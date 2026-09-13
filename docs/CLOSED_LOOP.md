# Closed-loop report (A–H)

Bitbank `btc_jpy` only. Default remains DRY_RUN. This file is the program
review for addition/removal and the closed-loop work.

## A. Issues and causes

| Symptom | Cause | Not a strategy bug |
| --- | --- | --- |
| `mode=DRY_RUN`, `bitbank_jpy_unchanged=true` | Default / no confirm string | Correct: paper only |
| `synthetic_fallback_no_orders` | Today’s `YYYYMMDD` 404 / code 10000 | Fetch yesterday; keep synthetic block |
| `candles loaded count=0` then thousands ready | Cache vs today’s empty date file | Cache is real history |
| `HOLD` / `no_buy_setup` | README MA gates not met | Valid WAIT; see `BUY_GATE` |
| `candle already processed` | Same closed bar on each poll | Evaluate once; heartbeat only |
| `SIGNAL_ONLY` | Flag (default false) | Stops before OrderExecutor |
| `run.py` on VPS | Stdlib screen, no Private API | Use `main.py` / `start.sh` |
| Assets unchanged after a BUY log | DRY_RUN / LIVE_READY / synthetic / HOLD | Not a silent Bitbank fill |

## B. Severity

| Item | Level |
| --- | --- |
| Blind retry of `POST /user/spot/order` | CRITICAL (fixed: no retry) |
| Synthetic bars used for LIVE | CRITICAL (blocked) |
| Dict `active_orders` treated as truthy | HIGH (fixed: list length) |
| Today candle 404 emptying the book | HIGH (fixed: also fetch yesterday) |
| `run.py` fallback while LIVE flags set | HIGH (fixed: start.sh refuses) |
| HOLD / no_buy_setup | LOW when market has no setup |

## C. Program review (added / removed / kept)

**Removed:** none.

**Added**

- `exchange/bitbank_adapter.py` — Bitbank facade; forwards to `RestClient`
- `managers.py` — Connection / Data / State / ExecutionMonitor
- `engine_state.py` — JSON `BotState`
- `trade_state.py` — WAIT → SIGNAL → ENTRY/EXIT_READY → ORDERING → PENDING/POSITION
- `trade_signal_executor.py` — single signal → gate → size → order
- `rate_engine.py`, `execution_gate.py`, `reconciliation.py`, `self_healing.py`, `sentry_setup.py`
- `RuntimeWatchdog` in `watchdog.py` — separate thread, no orders
- `tests/test_runtime.py`, `docs/PROMPT_INTAKE.md`, this file
- `src/bitbank_bot/paths.py`, `src/bitbank_bot/launch.py`, package `closed_loop.py`

**Kept:** `run.py`, README BUY1–4 / SELL1–4, `rest_client.py` as the only HMAC/HTTP layer.
`OrderExecutor` is the only live `create_order` caller.

## D. Modifications (why)

- LIVE is dual-flag + confirm. Missing confirm is LIVE_READY (`WOULD_SUBMIT_ORDER`).
- Candle errors log `CANDLE_API_ERROR` (no secrets). 404/10000 is not transient.
- Order and cancel POSTs are `side_effect=True` (no blind retry).
- Kill / halt can cancel a LIVE pending order.
- Circuit open and quarantine block new LIVE orders.
- Depth is logged before a live order; it does not change README prices.

## E. What lowered the dynamic integration rate

1. Running `run.py` instead of `main.py`.
2. DRY_RUN default (correct; JPY does not move).
3. Today’s 5min/1hour date file missing → empty fetch → synthetic → no orders.
4. HOLD when Granville/MA gates are false (correct).
5. Evaluating the same closed candle every poll (heartbeat, not a new bar).

## F. Tests (this environment)

- Full `pytest` on the package.
- Public ticker, yesterday 5min bars, today 404/10000, depth 200/200.
- `main.py --once --synthetic --skip-lock --no-screen` → HOLD, no `create_order`.
- `python3 src/bitbank_bot/main.py --check-config` works without `PYTHONPATH`.
- `python3 closed_loop.py` starts the bot; `--verify` is the review pass.
- No live POST: no keys in this VM.

## G. Remaining risks

- Private API, IP whitelist, and VPS NTP cannot be proven here.
- iTerm Shell Integration is Mac-local (`scripts/iterm_dev_env.zsh` only).
- RSI / MACD / Bollinger / Sakata are **not** in this bot. Do not invent them.
- LIVE on the VPS still needs the confirm string and min-lot human check.
- `data/KILL` must exist in ops runbooks.

## H. Pre-LIVE checklist

1. VPS runs `./start.sh`, `python3 main.py`, or `python3 closed_loop.py` (httpx). Do not run `run.py` for live.
2. Boot log: `DRY_RUN`, `LIVE_TRADING`, `LIVE_TRADING_CONFIRM`, `TRADING_MODE`, `may_place_live_orders`.
3. `LIVE_READY` first: `WOULD_SUBMIT_ORDER` on a real BUY/SELL.
4. Then LIVE + confirm + min lot `0.0001` BTC.
5. Watch `ORDER_ID_RECEIVED` → poll → fill → Bitbank balances.
6. Keep `data/KILL`. Rotate keys if they were pasted into chat.
