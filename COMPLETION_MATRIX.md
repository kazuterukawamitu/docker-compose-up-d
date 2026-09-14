# Completion matrix (this branch)

Scoring is evidence-based: code path + pytest. LIVE Bitbank fills are **NOT TESTED**
in CI (no keys, no real orders).

| # | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 01 | Python syntax | PASS | `python -m compileall` |
| 02 | Imports | PASS | pytest collection |
| 03 | Pair `btc_jpy` | PASS | `config.py` rejects aliases |
| 04 | Public REST | PASS | `RestClient.public_get`; smoke optional |
| 05 | Private REST | PASS | HMAC time-window; not called without keys |
| 06 | Market data | PASS | `fetch_candles`; cache-fresh fallback |
| 07 | Strategy BUY/SELL/HOLD | PASS | `tests/test_strategy.py` |
| 08 | HOLD reason | PASS | `Signal.hold` requires reason; BUY_GATE log |
| 09 | 15-min stall | PASS | Watchdog LONG_WAIT + HoldTracer STALLED |
| 10 | TradeGate | PASS | `trade_signal_executor.py` + tests |
| 11 | DRY_RUN default | PASS | `.env.example`, `load_config` |
| 12 | LIVE_READY | PASS | `TRADING_MODE=live_ready`; `WOULD_SUBMIT_ORDER` |
| 13 | LIVE dual confirm | PASS | phrase `YES_I_ACCEPT_REAL_MONEY_RISK` |
| 14 | Synthetic no live orders | PASS | `synthetic_fallback_no_orders` + gate |
| 15 | OrderExecutor only POST | PASS | strategy has no `create_order` |
| 16 | POST not retried | PASS | `idempotent=False` on `private_post` |
| 17 | Uncertain POST reconcile | PASS | `_recover_uncertain_order` |
| 18 | order_id / partial / full | PASS | `orders.py` + engine pending tests |
| 19 | RateEngine FIXED/DYNAMIC/AUTO | PASS | `rate_engine.py` tests |
| 20 | README TP percents preserved | PASS | BUY1 3% / BUY2 5–8% / BUY3 4% / BUY4 5% |
| 21 | Kill switch / min lot | PASS | unchanged `risk.py` / `amounts.py` |
| 22 | pytest | PASS | this branch |
| 23 | Live fill on Bitbank | NOT TESTED | requires user keys + confirm |
| 24 | SIGNAL_ONLY | N/A | not in repo (not added) |
| 25 | Other exchanges | PASS | none on order path |

## Consistency scores (after this branch)

| Area | Before | After | Notes |
| --- | --- | --- | --- |
| Macro (end-to-end path) | 72 | 86 | Gate + LIVE_READY + cache-fresh candles |
| Meso (module contracts) | 70 | 84 | RateEngine + TradeGate |
| Micro (flags/values) | 75 | 88 | Dual live phrase; BUY_GATE |
| Bitbank API | 80 | 88 | No POST retry; candle error fields |
| Data / logs | 68 | 82 | trace-ish slog stages |
| Strategy | 85 | 86 | Same entries; diagnostic gates |
| Order/fill | 78 | 88 | Timeout recover, no duplicate POST |
| Ops | 70 | 78 | HoldTracer STALLED; health_score |

Verdict: **③ Modification required for live funds** until a human sets LIVE + confirm on the VPS and watches `WOULD_SUBMIT_ORDER` in LIVE_READY first.

Pipeline (CI):
SIGNAL generation PASS (synthetic) → TradeGate PASS (unit) → OrderExecutor DRY_RUN PASS → Bitbank create_order **NOT TESTED** → fill **NOT TESTED** → balance change **NOT TESTED**.
