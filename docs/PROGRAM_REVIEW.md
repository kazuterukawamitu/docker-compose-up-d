# Program review (added / kept / not added)

## Added

| Path | Why |
| --- | --- |
| `src/bitbank_bot/rate_engine.py` | FIXED/DYNAMIC/AUTO TP and size policy; does not emit BUY/SELL |
| `src/bitbank_bot/trade_signal_executor.py` | TradeGate; `WOULD_SUBMIT_ORDER`; block reasons |
| `src/bitbank_bot/hold_tracer.py` | 15-minute STALLED + ROOT_CAUSE |
| `src/bitbank_bot/self_healing.py` | Error class + GET circuit breaker (no source rewrite) |
| `src/bitbank_bot/reconciliation.py` | Bitbank vs bot BTC/open-order compare |
| `scripts/ast_audit.py` | AST/import map → `reports/` |
| `MASTER_REQUIREMENTS.md` | De-duplicated spec |
| `COMPLETION_MATRIX.md` | Gap vs 100% |
| `docs/DEV_ENVIRONMENT.md` | iTerm/venv/VPS; no global zshrc |
| Tests `test_rate_and_candles.py`, `test_trade_gate.py` | New behavior |

## Modified (kept architecture)

`config.py`, `engine.py`, `orders.py`, `rest_client.py`, `market_data.py`, `strategy.py`, `amounts.py`, `indicators.py`, `screen.py`, `main.py`, `.env.example`, `tests/test_config.py`

## Removed

None. Wiki HTML in the repo root is still unused by the bot.

## Explicitly not added (would block or rewrite unsafely)

- `SIGNAL_ONLY` flag
- New cooldown lock
- Exchange adapters (bitFlyer / Coincheck / GMO)
- Auto-enabling LIVE
- Machine-wide `.zshrc`
- Sentry (no DSN in repo)
- Strategy relaxation to force BUY
