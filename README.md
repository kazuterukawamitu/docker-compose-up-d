# Bitbank BTC/JPY spot bot

Bitbank-only `btc_jpy` bot. Default is a **continuous DRY_RUN loop** with an iTerm **取引画面** (trading dashboard). HOLD/WAIT on a bar is normal. JSON lines are written to `logs/bot.log`, not the dashboard.

The runnable bot is in `src/bitbank_bot/` on branch `cursor/bitbank-closed-loop-1114` (and recent `main` after merge). Wiki HTML files in the repo root are leftover chart dumps and are not loaded.

HOLD for 15 minutes while market data and strategy are healthy is `LONG_WAIT`, not a crash. Public-API fallback candles never place orders. Live UNFILLED limits are persisted and polled. New BUY is blocked when both 4h and 1d SMA slopes are down (`ENABLE_HTF_FILTER`).

## Start (this is the program)

From the repository root (the folder that contains `main.py` and `closed_loop.py`):

```bash
python3 closed_loop.py --dry-run --skip-lock --no-screen --max-cycles 1
```

That command starts the full bot, prints `LAUNCH_OK`, runs one DRY_RUN cycle, and exits. HOLD / `no_buy_setup` is normal. Ctrl-C stops a continuous run.

Continuous 取引画面 (Mac iTerm, TTY):

```bash
bash ./start.sh --screen
```

The same bot also starts with:

```bash
python3 closed_loop.py
python3 main.py
python3 src/bitbank_bot/main.py
python3 -m bitbank_bot
python3 run.py
```

Checks that exit (no live orders):

```bash
python3 closed_loop.py --review
python3 closed_loop.py --verify --no-public
python3 closed_loop.py --verify
```

Live trading stays **off** unless `.env` has `DRY_RUN=false` **and** `LIVE_TRADING=true` **and** both API keys **and** `LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK`. Missing the confirm phrase stays in `LIVE_READY` (`WOULD_SUBMIT_ORDER` only). Default `RATE_MODE=fixed` keeps the README take-profit percents.

Bitbank’s public “today” candlestick file can 404 at JST midnight (code 10000). Incremental fetch also loads yesterday, and the loop keeps cached real bars instead of switching to synthetic no-orders. HOLD / `no_buy_setup` is a valid Granville miss; `BUY_GATE` logs which checks failed.

Contradiction resolution: [MASTER_REQUIREMENTS.md](MASTER_REQUIREMENTS.md). Evidence: [COMPLETION_MATRIX.md](COMPLETION_MATRIX.md).

`--once --synthetic` is a one-cycle smoke test that **exits on purpose**. The launcher above does **not** use `--once`.


## Strategy (from original README)

下降トレンドだった移動平均線が横ばいor上昇となり
Btcの価格が移動平均線を上抜けた時にbtcを可能量で買い
買った価格の➕３%で売る
移動平均線が上昇トレンド中に
Btcの価格が移動平均線を下抜けた時にbtcを可能量で買い
ゴールデンクロスの場合買った価格の➕８%で売る
ゴールデンクロス以外の場合買った価格の➕５％で売る
Btc価格が移動平均線よりも大きく５％以プラスに離れた後btc価格が下降したが移動平均線まで落ちずに
再び上昇した時にbtcを可能量で買い
買った価格の➕４％で売る
下降トレンドの移動平均線よりもbtc価格が５％以上マイナスに下降したが再び上昇した時にbtcを可能量で買い
買った価格の➕５％で売る
Btc価格が移動平均線を４％以上上昇した後下降した時に
btcを全て売る
Btc価格が下降して移動平均線クロスして下降した時に
btcを全て売る
下降トレンドの移動平均線をbtc価格がクロスして上昇した時に
Btcを全て売る
Btc価格が移動平均線よりも4％以上マイナス（extend all)に下降した後再度btc価格は上昇したが移動平均線まで上昇せずに再び下落した時に
Btcを全て売る

State-machine mapping: [docs/STRATEGY.md](docs/STRATEGY.md).

## Security

- Copy `.env.example` to `.env` is done by `start.sh` when missing. **Never commit `.env`.**
- If API keys were pasted into chat, **rotate them in the bitbank console**.
- `DRY_RUN=true` and `LIVE_TRADING=true` are mutually exclusive.
- Live POST also requires `LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK`.
- Create `data/KILL` to halt new orders.

## Tests

```bash
bash ~/docker-compose-up-d/start.sh --once --synthetic --skip-lock
PYTHONPATH=src .venv/bin/python -m pytest -q
```

Read-only execution check (never places an order):

```bash
python3 scripts/bitbank_execution_audit.py
```

Audit notes: [docs/AUDIT.md](docs/AUDIT.md).

systemd example (not installed by this repo): [deploy/bitbank-bot.service](deploy/bitbank-bot.service).

HTML GitHub wiki exports in the repo root are preserved as-is.
