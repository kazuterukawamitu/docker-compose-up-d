# Bitbank bot audit (this branch)

This repository on `main` is still a wiki HTML dump plus a strategy README. The
runnable bot lives in `src/bitbank_bot/`. This branch is Bitbank `btc_jpy` only.

## What exists

| Area | Where | Role |
| --- | --- | --- |
| Config / dual live flags | `config.py` | `DRY_RUN` default; live needs `DRY_RUN=false` and `LIVE_TRADING=true` and keys |
| Public + private REST | `rest_client.py` | HMAC `ACCESS-TIME-WINDOW`; `create_order` requires `live_confirmed` |
| README MA rules | `strategy.py`, `docs/STRATEGY.md` | BUY1–4 / SELL1–4; HOLD always has a reason |
| Size | `amounts.py` | Only place that sets quantity; TARGET vs PLANNED; ACTUAL unset until fill |
| Risk | `risk.py` | Kill switch, daily loss, position cap, circuit breaker |
| Orders | `orders.py` | DRY_RUN never calls `create_order`; live unfilled is polled |
| Loop | `engine.py` | Candles → signal → size → order; state in `data/state.json` |
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
2. **JST midnight empty “today” file.** Bitbank returns HTTP 404 / code 10000 for
   `/{pair}/candlestick/{type}/{YYYYMMDD}` until that calendar day has data.
   Incremental fetch now also loads **yesterday**. If the incremental call is
   still empty, cached real bars are kept and execution is **not** flipped to
   synthetic-no-orders. That was the `candles loaded count=0` plus thousands of
   cached bars inconsistency.
3. **CANDLE_API_ERROR.** Failed candle calls log pair, type, date, HTTP status,
   Bitbank code, and endpoint. Secrets are never logged.
4. **POST order is not GET-retried.** `create_order` uses a single attempt.
   Timeout inspects open orders instead of posting again.
5. **LIVE_READY.** `LIVE_TRADING=true` without
   `LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK` logs `WOULD_SUBMIT_ORDER`
   and does not POST.
6. **BUY_GATE / ROOT_CAUSE.** HOLD/`no_buy_setup` logs which Granville checks
   failed. 15-minute HOLD stays `LONG_WAIT` with a root cause.
7. **RateEngine.** `RATE_MODE=fixed|dynamic|auto` overlays TP/risk; default
   `fixed` keeps BUY1–4 percents.
8. **15-minute HOLD.** Healthy no-trade is `LONG_WAIT`, not a crashed bot.
9. **Live UNFILLED limits.** `accepted_unfilled` is stored in `state.pending`
   and polled via `GET /user/spot/order`. New signals wait until that order
   fills or remains open.
10. **4h + 1d filter.** New BUY is blocked when both higher-timeframe SMA slopes
    are DOWN, or when HTF candles cannot be read. Disable with `ENABLE_HTF_FILTER=false`.
11. **Empty / non-finite size.** `ensure_decimal` rejects empty/bool/NaN/Inf on
    the order path and names the field (never secrets).
12. **Missing state file.** `load_state` always initializes `pending` so a first
    boot cannot raise `NameError`.
13. **Audit script import path.** `python3 scripts/bitbank_execution_audit.py`
    adds `src/` itself; it no longer requires `PYTHONPATH`.
14. **Paper sells.** DRY_RUN sizes sells from the paper position, not static
    `DRY_RUN_FREE_BTC=0`, and flattens leftover dust at or below the min lot.
15. **Synthetic cache.** Accidental fallback bars are not merged into
    `CandleCache`, so a later real fetch cannot trade on mixed fake MAs.
16. **Partial fills.** `PARTIALLY_FILLED` stays in `state.pending` and is polled
    until the remainder fills.
17. **Kill file.** `data/KILL` blocks sells as well as buys.

## What this bot does not do

- Does not SSH to a VPS or install systemd for you.
- Does not implement quantum / multi-exchange / guaranteed fills or profits.
- Does not log API keys or secrets (`safe_dict` / `Config.__repr__`).
- Does not place a live order unless `DRY_RUN=false`, `LIVE_TRADING=true`,
  keys, and `LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK` are all set.

If keys were pasted into chat, rotate them in the bitbank console. Do not put
them in git, screenshots, or logs.
