# Completion matrix

Status is evidence-based: PASS / PARTIAL / FAIL / UNKNOWN.
“String exists in the repo” is not PASS.

| ID | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 01 | Python syntax | PASS | `python -m compileall` / pytest compile tests |
| 02 | Imports | PASS | package under `src/bitbank_bot`, `launch.py` adds `src/` |
| 03 | Pair `btc_jpy` | PASS | `config.normalize_pair`, rejected aliases |
| 04 | Public REST | PASS | `RestClient.public_get`, `tests/test_public_smoke.py` |
| 05 | Private REST auth | PASS | ACCESS-TIME-WINDOW HMAC; order POST needs `live_confirmed` |
| 06 | Market data | PASS | `fetch_candles` JST `YYYYMMDD` / year keys; `CANDLE_API_ERROR` logs |
| 07 | Strategy BUY/SELL/HOLD | PASS | `strategy.py` BUY1–4 SELL1–4; HOLD reason required |
| 08 | BUY_GATE diagnostics | PASS | `strategy._buy_signal` logs failing legs |
| 09 | 15-minute stall | PASS | `watchdog.LONG_WAIT`; STALLED log includes `last_block_reason` |
| 10 | Trade / execution gate | PASS | `execution_gate.py` → `TRADE_BLOCKED` / `WOULD_SUBMIT_ORDER` |
| 11 | DRY_RUN default | PASS | `load_config` default `dry_run=True` |
| 12 | SIGNAL_ONLY | PASS | not present; must not be added |
| 13 | Synthetic no live | PASS | `Engine.used_synthetic_fallback` sets `execute=False` |
| 14 | Balance / min size | PASS | `amounts.py`; `ORDER_BLOCKED` / plan.reason |
| 15 | Active orders | PASS | `get_active_orders` returns `orders` list; empty list is not blocking |
| 16 | OrderExecutor single path | PASS | strategy never calls REST order |
| 17 | `order_id` + fill states | PASS | UNFILLED persisted; PARTIALLY_FILLED polled |
| 18 | Dual live flags | PASS | `DRY_RUN=false` + `LIVE_TRADING=true` + keys |
| 19 | LIVE_READY | PASS | `LIVE_READY` / `--live-ready` |
| 20 | POST order no GET-style retry | PASS | `private_post(..., allow_retry=False)` for `create_order` |
| 21 | Timeout reconcile | PASS | failed `create_order` inspects `active_orders` before giving up |
| 22 | Rate modes | PASS | `RATE_MODE=fixed\|dynamic\|auto`; default fixed README TPs |
| 23 | WebSocket reconnect | PASS | exponential backoff in `websocket_client.py` |
| 24 | Kill switch | PASS | `KILL_SWITCH` / `data/KILL` |
| 25 | HTF BUY filter | PASS | 4h+1d; `--synthetic` skips |
| 26 | Unified launcher | PASS | `launch.py` + `start.sh` |
| 27 | Secrets | PASS | `safe_dict`, logging redact |
| 28 | pytest | PASS | `tests/` |
| 29 | Live order in CI | PASS | never; FakeRest / MagicMock |
| 30 | VPS systemd | PARTIAL | `deploy/bitbank-bot.service` example only |
| 31 | Sentry | FAIL | not added (no DSN; would leak if misconfigured) |
| 32 | Extra dip strategies | FAIL | deliberately not added (HOLD risk) |
| 33 | Mac `.zshrc` / iTerm5 | FAIL | not in this repo |

## Order path (actual)

```
launch.py / start.sh / main.py
  → Engine.run_forever
    → fetch_candles (Bitbank public) or synthetic (no execute)
    → Strategy.evaluate (BUY/SELL/HOLD + BUY_GATE)
    → HTF filter (live/dry real data only)
    → execution_gate
    → PositionSizer
    → RateEngine (TP / size_mult)
    → OrderExecutor.place
         dry_run → ORDER_INTENT / SIMULATED_FILL
         live_ready → WOULD_SUBMIT_ORDER
         live → RestClient.create_order(live_confirmed=True)
    → poll GET /user/spot/order until fill or still open
```

Live private API and real JPY/BTC movement are **NOT TESTED** in this cloud
agent (no keys, no live POST). Unit tests prove the live *path* calls
`create_order` when flags and a BUY/SELL signal are present.
