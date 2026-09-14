# Master requirements (Bitbank BTC/JPY bot)

This file is the de-duplicated specification distilled from the multi-part
prompt dump. It is the authority for this branch. It does **not** replace
`docs/STRATEGY.md` for BUY/SELL/TP percents.

## Contradiction resolution

| Conflict | Decision | Why |
| --- | --- | --- |
| “Reply only Please continue” vs “execute the whole request” | Execute. `END OF PROMPT` ends staging. | Cloud agent must finish the work. |
| “Remove every instruction that prevents buying” vs keep DRY_RUN / kill switch / min size | **Keep safety gates.** Log `TRADE_BLOCKED reason=…`. Never strip DRY_RUN, kill file, balance, min lot, synthetic-data ban, or dual live flags. | Real-money bot. Silent HOLD is the bug; safety is not. |
| “Aggressively place live orders when conditions match” vs “do not enable LIVE from DRY_RUN” | When `TRADING_MODE=live` **and** `LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK` **and** `DRY_RUN=false` **and** `LIVE_TRADING=true` **and** keys: a real BUY/SELL that passes TradeGate **must** call Bitbank `create_order`. Default remains DRY_RUN. | Dual authorization. No silent conversion of BUY→HOLD after the gate passes. |
| Pause for approval before RateEngine vs implement | Implement FIXED/DYNAMIC/AUTO **without** changing Granville/MA entry rules. | Rate layer is sizing/TP scaling only. |
| Rewrite into DataManager/ConnectionManager/… vs preserve architecture | **Do not rewrite.** Add modules and call them from `engine.py`. | Existing loop already is candles → strategy → risk → amounts → orders. |
| Mac `.zshrc` / iTerm5 shell integration vs VPS bot | Document in `docs/DEV_ENVIRONMENT.md`. Do not ship a machine-wide zshrc. | This repo is the bot, not the laptop. |
| SIGNAL_ONLY / cooldown locks | **Not present** in this codebase. Do not add blockers that do not exist. | Inventing SIGNAL_ONLY would stop orders. |
| Other-exchange adapters | None in the execution path. Bitbank `btc_jpy` only. | |

## Canonical architecture (as implemented)

```
MarketData (REST candles + optional WS ticker)
  → Strategy (README MA rules; BUY1–4 / SELL1–4 / TP / HOLD+reason)
  → RateEngine (FIXED | DYNAMIC | AUTO; does not emit BUY/SELL)
  → TradeGate (mode, real data, risk, size, duplicates)
  → OrderExecutor (only create_order call site besides RestClient)
  → Fill / pending poll
  → Position + paper or Bitbank balances
  → HoldTracer / Watchdog / Reconciliation
```

`run.py` remains a stdlib DRY_RUN dashboard. It never calls `create_order`.

## Trading modes

| Mode | Orders | Private API | Typical use |
| --- | --- | --- | --- |
| `DRY_RUN` (default) | Never | Optional | Continuous 取引画面 |
| `LIVE_READY` | Never. Log `WOULD_SUBMIT_ORDER` | Yes, if keys | Dress rehearsal |
| `LIVE` | Yes, after TradeGate | Required | Real funds |

LIVE cannot be enabled by a single flag.

## Rate modes

- **FIXED:** keep README TPs (BUY1 +3%, BUY2 +5% or +8% golden, BUY3 +4%, BUY4 +5%). Size = possible JPY amount.
- **DYNAMIC:** scale TP/SL and size from ATR%; clamp with MIN/MAX_* constants. Invalid ATR → no order.
- **AUTO:** RANGE/FLAT → FIXED; TREND → DYNAMIC; HIGH_VOL → DYNAMIC + smaller size.

## Non-goals

- Guaranteed profit, other exchanges, rewriting `run.py` into the full package, installing systemd on the VPS, dumping API secrets, placing live orders from CI or this Cloud Agent.
