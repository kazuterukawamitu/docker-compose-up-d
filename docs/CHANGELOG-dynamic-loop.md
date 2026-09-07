# Changelog — dynamic loop / live-ready pipeline

Running add/remove review for this branch.

## Added

- `src/bitbank_bot/execution_gate.py` — single pre-order gate (`EXECUTION_BLOCKED`).
- `src/bitbank_bot/rate_engine.py` — `RATE_MODE` fixed/dynamic/auto; preserves README TPs.
- `src/bitbank_bot/reconciliation.py` — Bitbank-source sync; ambiguous disables new orders.
- `src/bitbank_bot/connection.py` — REST/WS freshness and health score.
- `src/bitbank_bot/self_healing.py` — classify/retry GET/circuit/quarantine/kill/watch heartbeats.
- Tests: `test_trading_modes.py`, `test_execution_gate.py`, `test_rate_engine.py`, `test_reconciliation.py`, `test_self_healing.py`, `test_pipeline.py`, `test_candles.py`, `test_rest_retry.py`.

## Modified

- `config.py` — `TRADING_MODE`, `LIVE_TRADING_CONFIRM`, `RATE_MODE`, default `CANDLE_TYPE=5min`. LIVE never enabled by default.
- `market_data.py` — JST 5min keys, `CANDLE_API_ERROR`, no silent all-fail, cache `real` flag, 5min synthetic.
- `rest_client.py` — no blind POST retry; `OrderSubmitUncertain`; candlestick type match; `cancel_order`.
- `engine.py` — evaluate once per new close; Risk→Rate→Gate→Sizer→`ExecutionEngine.submit_order`; cache kept on fetch fail.
- `strategy.py` — `BUY_CHECK`/`BUY_GATE`, `signal_strength`, `WAIT`; gates not loosened.
- `amounts.py` — optional risk/SL sizing; `ORDER_BLOCKED` reasons.
- `orders.py` — `submit_order`, `WOULD_SUBMIT_ORDER`, verify-then-maybe-resend.
- `indicators.py` — RSI, MACD, ATR, ADX (diagnostics + RateEngine).
- `preflight.py`, `main.py`, `screen.py`, `logging_setup.py`, `multi_timeframe.py`, `websocket_client.py`.
- `.env.example`, `README.md`, `docs/STRATEGY.md`, `docs/AUDIT.md`, `pyproject.toml`, `requirements-dev.txt`.

## Removed

- Nothing. Wiki HTML and `run.py` stdlib launcher kept.

## Follow-up (test / slog hardening)

- `logging_setup.py` — `slog(..., message=)` no longer crashes the loop; extra text goes to `detail`.
- `self_healing.py` — error collector / task crash logs use `detail`.
- `orders.py` — ignore non-dict `get_order` responses after uncertain POST.
- Tests: candle fetch arg order, heartbeat-once evaluation, timeout recovery mock, public 5min today/yesterday.

## Not done (by design)

- Did not flip `DRY_RUN`→`LIVE`.
- Did not place live Bitbank orders.
- Did not rewrite personal macOS/iTerm5 configs.
- Did not convert the loop to asyncio (existing design is sync + WS thread).
