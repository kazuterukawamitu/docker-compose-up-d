# Bitbank bot audit (this branch)

This repository on `main` is still a wiki HTML dump plus a strategy README. The
runnable bot lives in `src/bitbank_bot/`. This branch is Bitbank `btc_jpy` only.

## What exists

| Area | Where | Role |
| --- | --- | --- |
| Config / dual live flags | `config.py` | `DRY_RUN` default; live needs `DRY_RUN=false` and `LIVE_TRADING=true` and keys. `LIVE_READY=true` blocks `create_order` |
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
12. **Canceled orders.** `CANCELED` / `CANCELED_UNFILLED` clear `state.pending` instead of leaving it unfilled forever.
13. **Partial-fill cost.** Added size uses cumulative notional minus the notional already booked, not new size times the cumulative average.
14. **Fees.** Reported quote/base fees (or `FEE_RATE` when the payload has none) are included in cost and deducted from sell proceeds.
15. **Same-candle exits.** A sell signal on an already processed bar still orders. Live price can take profit or hit `STOP_LOSS_PCT` without waiting for the next closed candle. `STOP` is a market order.
16. **Startup reconcile.** In live mode, one open exchange order is adopted and a local pending id missing from active orders is polled. DRY_RUN does not adopt.
17. **Launcher.** `run.sh` and `start.sh` do not run git. `/run.sh` is not a valid path.
18. **Empty active-order payload.** `{"orders": []}` is not treated as an open order.
19. **LIVE_READY.** `LIVE_READY=true` logs `WOULD_SUBMIT_ORDER` and never calls `create_order`. A simulated fill is ignored when `DRY_RUN` is off.
20. **BUY_GATE / candle errors.** A `no_buy_setup` bar logs which Granville gates failed. A candle fetch error logs pair, type, date, HTTP status, and Bitbank code, not the API secret.

## What this bot does not do

- Does not SSH to a VPS or install systemd for you.
- Does not implement quantum / multi-exchange / guaranteed fills or profits.
- Does not log API keys or secrets (`safe_dict` / `Config.__repr__`).
- Does not place a live order unless both flags and keys are set, and `LIVE_READY` is false.

If keys were pasted into chat, rotate them in the bitbank console. Do not put
them in git, screenshots, or logs.
