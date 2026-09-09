# Bitbank bot audit (this branch)

This repository on `main` is still a wiki HTML dump plus a strategy README. The
runnable bot lives in `src/bitbank_bot/`. This branch is Bitbank `btc_jpy` only.

## What exists

| Area | Where | Role |
| --- | --- | --- |
| Config / modes | `config.py` | `DRY_RUN` / `LIVE_READY` / `LIVE`; LIVE also needs confirm string + keys |
| Public + private REST | `rest_client.py` | HMAC `ACCESS-TIME-WINDOW`; order POST is not retried; candle errors logged |
| README MA rules | `strategy.py`, `docs/STRATEGY.md` | BUY1–4 / SELL1–4; HOLD always has a reason; `BUY_GATE` / `SELL_GATE` |
| RateEngine | `rate_engine.py` | `RATE_MODE=fixed\|dynamic\|auto`; strategy TPs preserved in FIXED |
| Size | `amounts.py` | Only place that sets quantity; DYNAMIC uses risk/SL distance |
| Risk | `risk.py` | Kill switch, daily loss, position cap, circuit breaker |
| Execution gate | `execution_gate.py`, `trade_signal_executor.py` | Single path; `EXECUTION_BLOCKED` / `WOULD_SUBMIT_ORDER` |
| Orders | `orders.py` | DRY_RUN never calls `create_order`; live unfilled is polled; no blind POST retry |
| Reconcile / heal | `reconciliation.py`, `self_healing.py` | Bitbank snapshot vs bot state; circuit breaker; error class |
| Loop | `engine.py` | Candles → signal → rate → gate → size → order; cache miss ≠ synthetic |
| Screen | `screen.py` | iTerm 取引画面; JSON stays in `logs/bot.log` |
| 4h+1d filter | `multi_timeframe.py` | Hard BUY block when both HTF SMAs slope down, or HTF data missing |
| Watchdog | `watchdog.py` | HOLD past 15 minutes is `LONG_WAIT`, not `FAIL` |
| Read-only audit | `scripts/bitbank_execution_audit.py` | ticker / assets / active_orders / trade_history |

`run.py` is a stdlib-only DRY_RUN 取引画面. It is the program that
runs with plain `python3` when pip/httpx/the feature-branch checkout
are missing. It never calls `create_order`.

bitFlyer, Coincheck, and GMO are not imported and are not executed.

## Redundancies (kept on purpose)

- `BALANCE_USAGE_RATIO` aliases `MAX_BALANCE_USAGE`.
- `LOOP_SECONDS` aliases `POLL_SEC`.
- `MA_SHORT_PERIOD` aliases `SHORT_MA_PERIOD`.
- `--once --synthetic` is a smoke exit; the launcher default is a continuous loop.
- Wiki HTML files in the repo root are leftover chart dumps and are not loaded.

## Order-path gaps this branch closes

1. **Accidental synthetic fallback.** If the public candle API fails, the loop
   used to evaluate *and execute* against generated bars. Execution is now off
   unless `--synthetic` was requested. Watchdog is `FAIL` / `synthetic_fallback_no_orders`.
2. **15-minute HOLD.** Healthy no-trade is `LONG_WAIT`, not a crashed bot.
3. **Live UNFILLED limits.** `accepted_unfilled` is stored in `state.pending`
   and polled via `GET /user/spot/order`. New signals wait until that order
   fills or remains open.
4. **4h + 1d filter.** New BUY is blocked when both higher-timeframe SMA slopes
   are DOWN, or when HTF candles cannot be read. Disable with `ENABLE_HTF_FILTER=false`.
5. **Empty / non-finite size.** `ensure_decimal` rejects empty/bool/NaN/Inf on
   the order path and names the field (never secrets).
6. **Missing state file.** `load_state` always initializes `pending` so a first
   boot cannot raise `NameError`.
7. **Audit script import path.** `python3 scripts/bitbank_execution_audit.py`
   adds `src/` itself; it no longer requires `PYTHONPATH`.
8. **Paper sells.** DRY_RUN sizes sells from the paper position, not static
   `DRY_RUN_FREE_BTC=0`, and flattens leftover dust at or below the min lot.
9. **Synthetic cache.** Accidental fallback bars are not merged into
   `CandleCache`, so a later real fetch cannot trade on mixed fake MAs.
10. **Partial fills.** `PARTIALLY_FILLED` stays in `state.pending` and is polled
    until the remainder fills.
11. **Kill file.** `data/KILL` blocks sells as well as buys.
12. **Latest candle miss used synthetic even with a real cache.** A failed
    `latest_only` public fetch no longer injects synthetic bars when the cache
    already holds real candles. Accidental synthetic still blocks orders.
13. **Candle errors were swallowed.** Failures now log `CANDLE_API_ERROR` with
    pair, type, date, HTTP status, Bitbank code, and retry count (never secrets).
    Bitbank returns HTTP 404 / code 10000 for *today's* `YYYYMMDD` until that
    date file exists (observed for `5min` and `1hour` on a new JST day).
    Latest-only fetches now also request yesterday so the book is not emptied.
14. **LIVE_READY.** Dual live flags without `LIVE_TRADING_CONFIRM` rehearse the
    full path and log `WOULD_SUBMIT_ORDER` instead of calling `create_order`.
15. **Order POST retry.** `POST /user/spot/order` is not retried on timeout;
    the bot reconciles open orders instead of sending a second BUY/SELL.

## What this bot does not do

- Does not SSH to a VPS or install systemd for you.
- Does not implement quantum / multi-exchange / guaranteed fills or profits.
- Does not log API keys or secrets (`safe_dict` / `Config.__repr__`).
- Does not place a live order unless `TRADING_MODE=live` (or dual flags) **and**
  `LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK` **and** keys are set.

If keys were pasted into chat, rotate them in the bitbank console. Do not put
them in git, screenshots, or logs.
