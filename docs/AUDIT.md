# Bitbank bot audit (this branch)

This repository on `main` is still a wiki HTML dump plus a strategy README. The
runnable bot lives in `src/bitbank_bot/`. This branch is Bitbank `btc_jpy` only.

## What exists

| Area | Where | Role |
| --- | --- | --- |
| Config / dual live flags | `config.py` | `DRY_RUN` default; live needs `DRY_RUN=false` and `LIVE_TRADING=true` and keys (or `TRADING_MODE=LIVE`) |
| V31 + OOS dual | `dual_run.py`, `v31.py`, `oos.py` | Production + shadow evaluators; OOS never orders |
| Evidence / timers | `evidence.py`, `loop_timers.py` | LIVE/private/order/OOS flags; shadow+guard active only while looping |
| Public + private REST | `rest_client.py` | HMAC `ACCESS-TIME-WINDOW`; `create_order` requires `live_confirmed` |
| README MA rules | `strategy.py`, `docs/STRATEGY.md` | BUY1–4 / SELL1–4; HOLD always has a reason |
| Size | `amounts.py` | Only place that sets quantity; TARGET vs PLANNED; ACTUAL unset until fill |
| Risk | `risk.py` | Kill switch, daily loss, position cap, circuit breaker |
| Orders | `orders.py` | DRY_RUN never calls `create_order`; live unfilled is polled |
| Loop | `engine.py` | Candles → signal → size → order; state in `data/state.json` |
| Decision | `decision.py` | Shannon entropy, fee-edge gate, ticker STOP/TP + daily PnL flatten |
| Quantum layer | `quantum_engine.py` | Bayesian scenarios, HOLD stagnation advice, anneal edge, self-heal guard |
| Screen | `screen.py` | iTerm 取引画面; JSON stays in `logs/bot.log` |
| 4h+1d filter | `multi_timeframe.py` | Hard BUY block when both HTF SMAs slope down, or HTF data missing |
| Watchdog | `watchdog.py` | HOLD past 15 minutes is `LONG_WAIT`, not `FAIL` |
| Sentry | `sentry_setup.py` | Optional via `SENTRY_DSN` (never hard-coded) |
| Read-only audit | `scripts/bitbank_execution_audit.py` | ticker / assets / active_orders / trade_history |
| Gap / bug agents | `scripts/gap_agent.py`, `bug_scan.py` | Purpose vs package; chan-pro style one finding per hit |
| Verify Docker agent | `scripts/verify_agent_loop.py` + compose profile `verify` | Continuous gap/bug/purpose checks on VPS |
| Purpose index | `scripts/purpose_index.py` | Python ↔ JSON instant search of module purposes |

`run.py` is a stdlib-only DRY_RUN 取引画面. It is the program that
runs with plain `python3` when pip/httpx/the feature-branch checkout
are missing. It never calls `create_order`. Paper mode mirrors the
patched exits: ticker STOP/TP, Shannon entropy, fee-aware daily PnL.
Use `scripts/gap_agent.py` and `scripts/bug_scan.py` to re-verify the
six production gaps after edits.

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
12. **Intra-bar exits.** A processed 1h candle used to skip every later poll.
    Stop (`STOP_LOSS_PCT`, default 2%) and take-profit now use the public last
    price on each loop and send a market sell. Pattern SELL1–4 still fire once
    per new closed candle.
13. **Cancel.** `CANCELED_UNFILLED` clears `pending`. A cancel with a partial
    fill books only the new slice, then clears the remainder.
14. **Partial-fill cost.** Added size is booked at
    `(new cumulative notional - previous notional) / new size`, not at the
    cumulative average.
15. **Fees.** Realized JPY subtracts quote fees. Trade-history
    `fee_amount_quote` / `fee_amount_base` win. Otherwise the taker rate
    (`TAKER_FEE_RATE`, default 0.12%) is applied and logged as estimated.
    Buys whose take-profit does not clear that round trip (widened by return
    entropy) are not sent.
16. **Startup reconcile.** Live mode polls a saved order, adopts an unknown
    active order (buy remainder **or open sell**), and adopts or resizes BTC
    from `free_amount` plus trade history. Dry-run does not rewrite state from
    the account.
17. **Stale sell limits.** A live sell still open after `SELL_UNFILLED_SEC`
    (default 20) is canceled and resent as a market order.
18. **Quantum-inspired layer.** Scenario probabilities, HOLD stagnation advice,
    anneal edge multiplier, and a self-healing guard are logged every decision.
    They never bypass risk or force a trade.
19. **Optional Sentry.** `SENTRY_DSN` only. Initialize from Python / `.env`,
    never by pasting `import` into zsh.

## BUY scarcity (2026-10-31 operator screen)

Operator Mac showed FLAT + `no_buy_setup` for ~14k cycles. Root cause: BUY4
required `Trend.DOWN` only while the market sat in FLAT, and the default dip was
5%. This branch allows BUY4 on DOWN/**FLAT** with default dip/extend **1%**.
Fee-edge and HTF filters still gate new buys. Size remains
`free_amount * MAX_BALANCE_USAGE` (realtime upper bound).

## What this bot does not do

- Does not SSH to a VPS, install Docker there, or install systemd for you.
- Does not place a live order unless both flags and keys are set on the machine that runs the bot.
- Does not promise a profit. A long `HOLD` / `no_buy_setup` streak means the MA rules were not met.
- Does not implement multi-exchange routing or guaranteed fills.
- Does not log API keys or secrets (`safe_dict` / `Config.__repr__`).
- Does not solve the halting problem; correctness is runtime-verified continuously.
- Does not use quantum hardware; `quantum_engine.py` is classical adaptive search.
- Does not report LIVE / Private API / shadow-timer YES without evidence (`evidence.py`).

If keys were pasted into chat, rotate them in the bitbank console. Do not put
them in git, screenshots, or logs.
