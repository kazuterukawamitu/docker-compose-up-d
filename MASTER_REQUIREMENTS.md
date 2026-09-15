# Master requirements (consolidated)

This file is the single spec extracted from the multi-part prompt.
Contradictions are resolved here; the bot follows this file, not every
sentence of the original dump.

## Product

Bitbank-only BTC/JPY (`btc_jpy`) spot bot. Existing README moving-average
rules (BUY1–4 / SELL1–4 with +3% / +5% / +8% / +4% take-profits) stay
authoritative. Success means the closed loop works, not that trades profit.

## Safety (this beats every later instruction)

1. Default remains `DRY_RUN=true`. This environment does not send live orders.
2. Live `create_order` requires **all** of: `DRY_RUN=false`, `LIVE_TRADING=true`,
   keys present, and `LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK`.
3. Missing confirm phrase → `TRADING_MODE=live_ready` (WOULD_SUBMIT_ORDER only).
4. Synthetic / fallback market data must never place live orders.
5. POST `/user/spot/order` is not retried like GET. After a submit timeout,
   open orders are inspected before any new POST.
6. The instruction to “execute actual orders aggressively” is **rejected**.
   It contradicts dual-authorization, fund safety, and this repo’s existing
   live gate.

## Closed loop

Market data → strategy signal → RateEngine → Risk / PositionSizer →
TradeGate (`trade_signal_executor.py`) → `OrderExecutor` → Bitbank →
order_id / poll / partial / fill → paper or exchange ledger → reconcile.

`HOLD` / `no_buy_setup` is valid when Granville conditions are false.
Do not relax BUY/SELL rules to force a trade.

## Modes

| Mode | Orders |
| --- | --- |
| `dry_run` | No Bitbank POST. Optional paper fill. |
| `live_ready` | Full private/public path except POST order. Logs `WOULD_SUBMIT_ORDER`. |
| `live` | POST only after the confirm phrase and dual flags. |

`RATE_MODE=fixed|dynamic|auto`. Default `fixed` keeps existing TP percents.
`dynamic` / `auto` may rescale TP/SL with ATR, clamped. Invalid ATR blocks.

## Runtime diagnosis

- `CANDLE_API_ERROR` logs pair, type, date, HTTP status, Bitbank code (no secrets).
- Latest candle fetch includes **yesterday** so JST midnight 404 on “today”
  does not empty the book.
- If incremental fetch is empty but `CandleCache` has real bars, keep them
  and do **not** enter `synthetic_fallback_no_orders`.
- 15-minute HOLD is `LONG_WAIT` with `ROOT_CAUSE`, not a crash.
- `BUY_GATE` logs which Granville checks failed.

## Out of scope (recorded, not built in this change)

- Rewriting the bot as DataManager/ConnectionManager microservices
- Adding a dozen new pullback strategies without backtest approval
- Sentry SDK (no DSN; do not add a required dependency)
- Editing the operator’s macOS `~/.zshrc` (optional snippet only)
- Concatenating every `.py` into an executable all-in-one file
- Guaranteeing profit, VPS SSH, or systemd install
