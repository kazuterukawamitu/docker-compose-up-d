# Completion matrix

Evidence from this branch’s tests and a public-API probe. Live private
order POST was **not** executed (no keys, DRY_RUN default).

| ID | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 01 | Python syntax | PASS | `python3 -m compileall src` |
| 02 | Imports | PASS | pytest collection |
| 03 | Pair `btc_jpy` | PASS | `config.py` rejects aliases; tests |
| 04 | Public ticker | PASS | `tests/test_public_smoke.py` + live ticker last |
| 05 | Public 5min candles | PASS | Probe: today JST can 404 code 10000; yesterday has rows. Fetch now includes yesterday |
| 06 | Private API | PARTIAL | HMAC + `live_confirmed` tests; no keys in this environment |
| 07 | Strategy BUY/SELL/HOLD | PASS | `tests/test_strategy.py`; BUY_GATE logs |
| 08 | HOLD reason | PASS | `Signal.hold` requires reason; BUY_GATE |
| 09 | 15-minute stall | PASS | Watchdog LONG_WAIT + `root_cause` |
| 10 | TradeGate | PASS | `execution_gate.py` + `trade_signal_executor.py` |
| 11 | DRY_RUN default | PASS | `load_config` / `.env.example` |
| 12 | LIVE_READY | PASS | Missing confirm phrase; WOULD_SUBMIT_ORDER |
| 13 | SIGNAL_ONLY | PASS | Config flag; gate reason `SIGNAL_ONLY` |
| 14 | Synthetic block | PASS | Accidental fallback still disables execute; cache-real path does not |
| 15 | Balance / min amount | PASS | `amounts.py` tests |
| 16 | Active orders | PASS | `get_active_orders` list; empty list is not “active” |
| 17 | OrderExecutor | PASS | Single POST path via TradeSignalExecutor |
| 18 | order_id / unfilled poll | PASS | `tests/test_engine.py` pending tests |
| 19 | Partial fill | PASS | pending `filled_amount` |
| 20 | Duplicate POST retry | PASS | update/POST attempts=1; timeout adopts open order |
| 21 | TP mapping BUY1–4 | PASS | Unchanged strategy percents in FIXED |
| 22 | DYNAMIC/AUTO rates | PASS | `rate_engine.py` tests; ATR invalid blocks |
| 23 | Kill switch | PASS | existing `risk.py` |
| 24 | WS reconnect | PASS | existing exponential backoff |
| 25 | pytest | PASS | full suite |
| 26 | Live fill / balance move | NOT TESTED | Requires operator confirm + keys on VPS |

## Path trace (DRY_RUN, this environment)

| Stage | Result |
| --- | --- |
| Market data | PASS (public ticker); 5min “today” may 404 at JST midnight |
| Candles | PASS when yesterday included / cache kept |
| Indicators | PASS |
| Strategy | PASS — HOLD/`no_buy_setup` when gates fail |
| RateEngine | PASS (default FIXED) |
| Risk / size | PASS |
| TradeGate | PASS — DRY_RUN / LIVE_READY block POST |
| Bitbank create_order | NOT REACHED (correct) |
| Fill / balance | SIMULATED_FILL only in DRY_RUN |

## Consistency scores (judgment, not a lab metric)

| Area | Before | After |
| --- | --- | --- |
| Macro closed loop | 55 | 78 |
| Module wiring | 70 | 82 |
| Bitbank public candles | 40 | 85 |
| Order/fill distinction | 80 | 86 |
| Strategy (unchanged rules) | 85 | 88 |
| Ops / HOLD diagnosis | 60 | 80 |
| Live money path | 0 (not enabled) | 0 (still not enabled) |

Live trading remains **prohibited** until a human sets the confirm phrase on the VPS.
