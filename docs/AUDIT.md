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
12. **Terminal order status.** `CANCELED_UNFILLED` and the other cancel/reject statuses clear `state.pending`. A zero fill is no longer stored as `UNFILLED`, which had blocked every later order.
13. **Sell size.** A live sell is `min(free BTC, tracked position)`. Extra wallet BTC is not an exit order.
14. **Fixed lot.** Buys default to `0.001` BTC (`FIXED_ORDER_BTC`), the same lot the backtest uses. Possible-amount sizing remains available by setting the cap to `0`.
15. **Exit timeout.** A resting sell older than `SELL_ORDER_TIMEOUT_SEC` (default 30) is canceled and can be replaced on the same closed candle. A resting buy uses `PENDING_ORDER_TIMEOUT_SEC` (default 900).
16. **Hard stop.** `STOP_LOSS_PCT` (default 3%) is evaluated before the pattern sells.
17. **Quote age and assets.** A public ticker older than `QUOTE_MAX_AGE_SEC` blocks a new order. Keyed balance reads use one assets request.
18. **Readiness.** `live_ready` stays false unless both live flags, both keys, the 0.001 lot, a stop, and no kill switch are set. The report does not place an order.
19. **Partial-fill cost.** A later fill is booked as the new cumulative notional minus the previous cumulative notional. The pending order stores the cumulative average for the next increment.
20. **Fees.** Realized PnL and the paper JPY ledger deduct `TAKER_FEE_RATE` (default 0.12% per fill, about 0.24% round trip). Gross `actual_execution_jpy` stays the exchange notional. A buy whose take-profit does not clear that round trip is not sent.
21. **Live mark exit.** When the public ticker has a timestamp, a position at the stop uses `STOP_ORDER_TYPE` (default market) and a position at its take-profit uses a limit. Pattern BUY/SELL still use the closed candle. A quote with no timestamp is not a mark.
22. **Startup reconcile.** With API keys, and outside `--synthetic`, a missing local pending order is cleared only when the exchange says it is canceled. An exchange order with no local pending row is adopted so a second order is not sent. A full fill stays pending for the poll to book. Extra free BTC is logged and is not sold.
23. **Daily PnL and entropy.** The daily loss floor and an optional `DAILY_PROFIT_TARGET` block new buys only. Shannon entropy and the down posterior block a new buy after 8 return samples. Neither forces a sell. The iTerm screen shows 日次損益, entropy, and the HOLD reason.
24. **Offline slope note.** Backtest reports a suggested slope from a short search. That search does not write `MA_SLOPE_THRESHOLD` on the live bot.

This tree does not SSH to a VPS and does not restart a running bot. Applying it to a live process is a separate operator step after the service is stopped. The names in `adaptive.py` are ordinary probability and search helpers. They do not run a quantum computer and they do not submit orders.

## What this bot does not do

- Does not SSH to a VPS or install systemd for you.
- Does not run a quantum computer, a second exchange, or a guaranteed-profit model.
- Does not log API keys or secrets (`safe_dict` / `Config.__repr__`).
- Does not place a live order unless both flags and keys are set.

If keys were pasted into chat, rotate them in the bitbank console. Do not put
them in git, screenshots, or logs.
