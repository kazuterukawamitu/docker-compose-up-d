# Analysis (this branch)

Inventory of `/workspace` on `main`, then the minimal work on this branch.

## What main actually contained

- No Python bot: no `main.py`, no `diagnostics.py`, no `src/`.
- README with Docker locale snippets plus the Japanese moving-average buy/sell rules.
- GitHub wiki HTML dumps (`ビットコイン*.html`) — identical footer pages, not charts.
- Placeholder CI (`echo Hello, world!`).
- Leftover other-exchange (GMO / Coincheck / bitFlyer): **none**.

Prior draft PRs already implemented a Bitbank-only bot. The most complete tree is PR #8 (on top of the iTerm15 suite). This branch **reuses that architecture** instead of rewriting.

## Current architecture (kept)

```
market data (REST candles + WS ticker/trades/depth)
  → README MA strategy (R1–R8)  [no exchange calls]
  → RiskManager (kill, daily loss, size cap)
  → PositionSizer (free_amount, Decimal, 0.0001 BTC, 1 JPY tick)
  → OrderExecutor (DRY_RUN never calls create_order)
  → order_id / status / fill
  → local ledger + realized PnL
```

Entry: `python3 -m bitbank_bot`, `python3 main.py`, `bash ./start.sh`.
Default: `DRY_RUN=true`. Live requires `DRY_RUN=false` **and** `LIVE_TRADING=true` plus keys.

## Amount model (one)

**Model A — recalc from latest `free_amount` immediately before each order.**

- Buy: `available_jpy * MAX_BALANCE_USAGE * (1 - FEE_BUFFER) / price`, floored to 0.0001 BTC.
- Sell: all free BTC × 0.999 (spot flatten, no short).
- `BALANCE_USAGE_RATIO` is an alias for `MAX_BALANCE_USAGE` (canonical default **0.95**).
- `AmountPlan.target_jpy` / `planned_order_jpy` / `actual_execution_jpy` are **telemetry labels**, not a second sizer.
- Model B (`BUY_AMOUNT_MULTIPLIER=0.001`) is **not** implemented.

RiskManager may only **reduce** size. Invalid amount → no order.

## Gaps vs the concatenated prompt (what this branch changes)

| Gap | Change |
| --- | --- |
| Root `main.py` / `diagnostics.py` missing | Thin launchers; diagnostics never orders |
| MACD / RSI / ATR / Bollinger | Added in `indicators.py`; strategy still uses SMA/EMA |
| Strategy plugins unused | Advisory plugins (Granville, Sakata, MA cross, regime). **Orders still come only from README R1–R8** |
| Failed balance fetch / auth failure | Hard no-order; auth latches until restart |
| Stale WS | Skip **orders only** (retry candle; do not log TRADE SUCCESS) |
| Circuit breaker / max DD | Consecutive API errors; optional `MAX_DRAWDOWN_JPY` (0 = off) |
| WS trades/depth | Cached last trades + last depth (ticker already cached) |
| systemd / `.env.example` / `.gitignore` | Already present; branch names and aliases updated |

## What we will NOT change

- Sync `httpx` (no asyncio rewrite).
- README R1–R8 percents and SELL > TP > BUY priority.
- Dual confirmation for live trading.
- Wiki HTML dumps.
- Enabling live trading.
- GMO / Coincheck / bitFlyer.
- Claiming the Sakura VPS was tested (this environment cannot SSH there).
- Inventing profits: `[SIGNAL]` ≠ `[ORDER_ACCEPTED]` ≠ `[FILL]` ≠ `[SIMULATED_FILL]`.
