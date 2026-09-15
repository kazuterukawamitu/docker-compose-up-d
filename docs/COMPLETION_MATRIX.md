# Completion matrix

Status vs the synthesized master requirements. Evidence is tests
and code paths, not string presence.

| ID | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 01 | Python syntax | PASS | `tests/test_startup.py::test_compileall_src` |
| 02 | Imports | PASS | pytest collection |
| 03 | `btc_jpy` only | PASS | `config.PAIR`, rejected aliases |
| 04 | Public API | PASS | `run.py` / `market_data.fetch_candles_detailed` |
| 05 | Private API auth | PASS | `rest_client` HMAC headers; secrets never logged |
| 06 | Market data | PASS | ticker + candlestick + cache `real=` |
| 07 | SignalEngine | PASS | `strategy.Strategy.evaluate` |
| 08 | BUY generation | PASS | BUY1–4 + BUY_GATE logs |
| 09 | SELL generation | PASS | SELL1–4 + SELL_GATE logs |
| 10 | HOLD reason | PASS | `Signal.hold(reason)` + screen |
| 11 | 15-min stall | PASS | `watchdog` LONG_WAIT at 900s |
| 12 | Execution gate | PASS | `execution_gate.py` |
| 13 | DRY_RUN default | PASS | `.env.example`, `Config.dry_run` |
| 14 | LIVE_READY | PASS | `WOULD_SUBMIT_ORDER` |
| 15 | Dual LIVE confirm | PASS | phrase + keys + TRADING_MODE |
| 16 | Synthetic no live | PASS | `market_data_real` + gate |
| 17 | Balance check | PASS | `amounts.py` + `_balances` |
| 18 | Active orders | PASS | `OrderExecutor.active_orders` + gate `open_order_conflict` |
| 19 | Cooldown / pending | PASS | `state.pending` blocks new orders |
| 20 | RiskManager | PASS | kill, daily loss, drawdown, breaker |
| 21 | OrderExecutor | PASS | only POST caller |
| 22 | order_id | PASS | live `create_order` + pending |
| 23 | Status tracking | PASS | `get_order` poll |
| 24 | Partial fill | PASS | PARTIALLY_FILLED stays pending |
| 25 | FULLY_FILLED | PASS | pending cleared on fill |
| 26 | Reconcile | PASS | `reconciliation.py` |
| 27 | Duplicate prevent | PASS | pending + open-order conflict + POST no-retry |
| 28 | TP 3/4/5/8% | PASS | FIXED RateEngine + strategy |
| 29 | DYNAMIC/AUTO | PASS | ATR clamp + size_mult |
| 30 | Kill switch | PASS | `data/KILL` / `KILL_SWITCH` |
| 31 | WS reconnect | PASS | `websocket_client.py` |
| 32 | Candle errors | PASS | `CANDLE_API_ERROR` |
| 33 | Enhanced launcher | PASS | `start.sh` + `launch.py` |
| 34 | pytest | PASS | this matrix’s test run |
| 35 | Live POST in CI | NOT TESTED | requires user keys + dual-auth; not executed here |
| 36 | AST reports | PASS | `scripts/analyze_ast.py` → `reports/ast_report.json` |
| 37 | Source dump (not executable) | PASS | `scripts/dump_all_source.py` |
| 38 | File inventory | PASS | `reports/FILE_INVENTORY.md` |
| 39 | `BitbankAPIClient` façade | PASS | `api_client.py`; OrderExecutor still the POST caller |
| 40 | completion_percent | PASS | `scripts/completion_percent.py` (live POST skipped) |

LIVE Bitbank POST is **not** claimed PASS. DRY_RUN paper fills and
LIVE_READY `WOULD_SUBMIT_ORDER` are tested.
