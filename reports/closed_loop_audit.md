# Closed-loop audit (this branch)

Bitbank `btc_jpy` only. This pass adapted the existing `src/bitbank_bot`
loop. It did not invent a DataManager / ConnectionManager / multi-exchange
stack.

## A. Issues / causes

1. `fetch_candles` swallowed per-day exceptions, logged `candles loaded count=0`,
   then the loop fell back to synthetic bars and blocked orders. A warm
   `CandleCache` could still hold thousands of real closed bars (e.g. 14×288
   5-minute candles ≈ 3900), which looked like “closed candles ready” while
   fetch said 0.
2. `latest_only` fetched only today. Near JST midnight a 5-minute series can
   have zero *closed* bars for the new date.
3. Modes were `DRY_RUN` / `LIVE_TRADING` only. There was no `LIVE_READY`
   would-submit state and no `LIVE_TRADING_CONFIRM` phrase.
4. Heartbeat always printed REST/MARKET OK even after a failed ticker/candle
   fetch.
5. `HOLD` / `no_buy_setup` had a reason string but no BUY_GATE / SELL_GATE
   condition breakdown (users read “no signal” as a dead loop).
6. `RestClient._request` retried POST (including `create_order`) on transport
   / 5xx, which can double-submit.
7. No periodic Bitbank-vs-local reconcile.

## B. Severity

| Item | Severity |
| --- | --- |
| Empty 5m fetch → synthetic ban while cache is real | High (false “no orders” / weak dynamic loop) |
| Midnight date-boundary miss | High for `CANDLE_TYPE=5min` |
| POST retry | High if LIVE is ever enabled |
| Mode dual-auth / LIVE_READY | High (safety + dead-gate) |
| Stale ticker vs candle | Medium |
| Honest heartbeat / BUY_GATE logs | Medium |
| Reconcile | Medium |
| RateMode DYNAMIC halt | Low (FIXED default; strategy TPs unchanged) |

## C. Modified / added / removed files

**Added:** `execution_gate.py`, `trade_signal_executor.py`, `reconciliation.py`,
`rate_engine.py`, tests for modes/gate/candles/reconcile/rate/POST,
`reports/closed_loop_audit.md`.

**Modified:** `config.py`, `rest_client.py`, `market_data.py`, `orders.py`,
`engine.py`, `strategy.py`, `indicators.py`, `preflight.py`, `screen.py`,
`main.py`, `multi_timeframe.py`, `.env.example`, `README.md`, `docs/AUDIT.md`,
`tests/helpers.py`, existing tests.

**Removed:** none.

## D. Modification details

- Candle fetch logs `CANDLE_API_ERROR` (endpoint / http_status / bitbank_code /
  pair / candle_type / date / retry_count). Exceptions are not swallowed as a
  silent empty list when every date fails. Yesterday is always requested for
  short candle types. Cache is used when the latest fetch is empty/error and
  cached bars are real and fresh. Synthetic is never merged into the cache.
- `market_data_real` is true only for Bitbank candles. Accidental synthetic
  → `EXECUTION_BLOCKED` `synthetic_market_data`.
- Modes: `DRY_RUN` / `LIVE_READY` / `LIVE`. LIVE requires
  `TRADING_MODE=LIVE` and `LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK`
  and keys. Then `OrderExecutor` calls `create_order(..., live_confirmed=True)`
  with no extra dead gate. LIVE_READY logs `WOULD_SUBMIT_ORDER` only.
- `ExecutionGate` + `TradeSignalExecutor` sit in front of the existing
  `OrderExecutor`. Strategies still do not call Bitbank order APIs.
- BUY_GATE / SELL_GATE logs trend, crossover, volume, and per-rule flags.
  Strategy thresholds were not relaxed.
- POST `/user/spot/order` is not retried. After a submit exception the executor
  inspects `active_orders` and never POSTs again.
- Periodic `reconcile()` treats Bitbank balances / open orders as source of
  truth and logs `RECONCILE_MISMATCH`.
- `RateEngine` default FIXED keeps BUY1 3% / BUY2 5% or 8% / BUY3 4% / BUY4 5%.
  DYNAMIC halts on stale data or ATR NaN/0. AUTO falls back to FIXED.

## E. What reduced dynamic integration

The public candle path failed closed (empty or exception) → synthetic fallback
→ execute=false, while the screen/strategy still evaluated a cached or
synthetic series. HOLD/`no_buy_setup` and HTF blocks are also normal no-trade
outcomes; they were easy to confuse with a broken order loop.

## F. Test results

`python3 -m compileall` PASS. `PYTHONPATH=src pytest` **136 passed**.
Public Bitbank `btc_jpy` ticker + `5min` YYYYMMDD (today and yesterday, JST)
succeeded from this VM. No private order POST. Cloud tests stay dry-run /
mocked / public API only.

## G. Remaining risks

- LIVE still needs real keys and the confirm phrase on the VPS `.env`.
- HTF 4h+1d filter still blocks BUY when those slopes are down or HTF fetch
  fails (`ENABLE_HTF_FILTER=false` to disable).
- Limit orders can stay `UNFILLED`; JPY/BTC only move after a fill poll.
- `run.py` stdlib launcher remains DRY_RUN-only (no private orders).
- No profit guarantee.

## H. Pre-deployment checklist

1. Copy `.env.example` → `.env` on the VPS. Do not commit `.env`.
2. Keep `TRADING_MODE=DRY_RUN` until paper path looks correct in `logs/bot.log`.
3. Confirm public `GET /btc_jpy/candlestick/5min/YYYYMMDD` (JST) if you set
   `CANDLE_TYPE=5min`.
4. Confirm `CANDLE_API_ERROR` is absent and `market_data_real=true`.
5. To go LIVE: keys + `TRADING_MODE=LIVE` +
   `LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK`. Both required.
6. Touch `data/KILL` to halt. One instance (`data/bot.lock`).
7. Watch `WOULD_SUBMIT_ORDER` in LIVE_READY before enabling LIVE.
8. After a LIVE order: `order_id` → UNFILLED/PARTIAL/FULL → balance reconcile.

## Architecture (actual names)

```
main.py / bitbank_bot.main
  → load_config
  → RestClient
  → preflight
  → Engine.run_forever / run_once
      → fetch_candles_detailed (market_data) / CandleCache
      → process_candles → Strategy.evaluate (BUY_GATE/SELL_GATE)
      → evaluate_htf
      → ExecutionGate (via TradeSignalExecutor)
      → RateEngine (FIXED default)
      → PositionSizer / RiskManager
      → OrderExecutor.place  # only create_order caller
      → pending poll / reconcile
      → watchdog / screen
```

## Order path status (code)

| Stage | Status |
| --- | --- |
| Signal | PASS (existing Strategy) |
| Gate | PASS (`ExecutionGate`) |
| DRY_RUN order API | BLOCKED (`ORDER_INTENT` / simulated paper) |
| LIVE_READY order API | BLOCKED (`WOULD_SUBMIT_ORDER`) |
| LIVE dual-auth order API | PASS (`create_order` + `live_confirmed=True`) |
| Fill tracking | PASS (`order_id`, UNFILLED / PARTIAL / FULL) |
| Reconcile | PASS (periodic; Bitbank SoT) |
| Synthetic execute | BLOCKED |
| This VM live POST | NOT_REACHED (safety) |

## Completion vs 100% spec

Honest estimate: **~75%** of the user’s closed-loop spec on the *existing*
architecture. Delivered: candle error path, synthetic ban, modes + dual-auth,
gate, would-submit, no POST retry, fill poll, reconcile, BUY_GATE logs,
FIXED/DYNAMIC/AUTO without collapsing TPs, 5m date keys. Not delivered (on
purpose): new Granville alternatives, invented manager stack, Sentry (not in
repo), iTerm/zsh host integration, live orders from this VM.

## Consistency

- Safety vs prompt: high (dual-auth, no secret logging, synthetic ban kept).
- Architecture vs main: high (Engine / OrderExecutor / RestClient preserved).
- Prior mega-PRs: low on purpose (those added ConnectionManager / ADX regime /
  Sentry / iTerm launchers). This branch stays minimal.

## Strategy catalog (existing only; no new maxims)

BUY1 +3%, BUY2 +5% or +8% golden, BUY3 +4%, BUY4 +5%, SELL1–4, TP, HTF 4h+1d
BUY block. Candidates *not* added this pass: buy-the-dip extras, scoring,
multi-exchange.

---

## Second pass (full-program review)

Review requested after two incomplete pasted diffs. `ReconcileReport` already
had `bitbank_btc`, `local_btc`, `open_orders`, and `mismatches`. The pasted
`market_data.py` hunk had no real change. This pass inspected the existing
program and fixed confirmed bugs only.

### Bugs found and fixed

| Bug | Severity | Fix |
| --- | --- | --- |
| `if active:` treated `{"orders": []}` as open orders; `id → order` maps crashed `.get` | High | `coerce_active_orders()` in RestClient / OrderExecutor / reconcile. Empty dict → no orders. Unknown type raises (refuse live POST). |
| BTC mismatch only when `local > 0` (flat local + Bitbank BTC ignored) | High | Flag when `abs(bitbank_btc - local_btc) > min_amount_btc`. Do not overwrite `state.position` from free BTC. |
| Engine discarded `ReconcileReport` | High | `_apply_reconcile_report`: set `last_block_reason`, clear `pending_missing`, poll `pending_filled_unapplied`. |
| Pending FULLY_FILLED / Bitbank `CANCELED_UNFILLED` never flagged | High | `pending_filled_unapplied` vs `pending_missing` (Bitbank statuses). |
| Candle raise used a redundant `not any(...)` on the same list | Medium | `if not candles and last_error is not None: raise last_error`. |
| Naive / UTC `now` produced wrong YYYYMMDD keys; `lookback_days=0` skipped today | High for 5min | `as_jst()`; `days = max(1, lookback_days)`. |
| REST `data` can be `None` / non-dict; `.get` crashed | Medium | `_as_dict`; JSON payload must be a dict; candlestick first row guarded. |
| ExecutionGate reason `kill_switch_clear` vs risk `kill_switch` | Low | Map failed check to `kill_switch`. |
| `_poll_pending` swallowed balance errors | Low | Log exception type; still use ZERO/ZERO. |

Dataclass fields are populated and consumed (engine + RECONCILE logs). No unused stubs.

### Files changed this pass

**Modified:** `rest_client.py`, `orders.py`, `reconciliation.py`, `engine.py`,
`market_data.py`, `execution_gate.py`, `tests/test_reconciliation.py`,
`tests/test_orders.py`, `tests/test_candle_fetch.py`,
`tests/test_execution_gate.py`, `tests/test_engine.py`,
`tests/test_rest_retry.py`, `reports/closed_loop_audit.md`.

**Added / removed:** none.

### Test results (this pass)

Recorded after `compileall` + `pytest`. Public GET only; no live POST.
