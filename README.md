# Bitbank BTC/JPY spot bot

Bitbank-only `btc_jpy` bot. Default is a **continuous DRY_RUN loop** with an iTerm **取引画面** (trading dashboard). HOLD/WAIT on a bar is normal. JSON lines are written to `logs/bot.log`, not the dashboard.

`main` on GitHub is still wiki HTML. The runnable bot is this checkout (`src/bitbank_bot/`). Start it with `./bitbank-bot`.

HOLD for 15 minutes while market data and strategy are healthy is `LONG_WAIT`, not a crash. Public-API fallback candles never place orders. Live UNFILLED limits are persisted and polled. New BUY is blocked when both 4h and 1d SMA slopes are down (`ENABLE_HTF_FILTER`).

## Start (this is the program)

From the repo root, run the executable:

```bash
./bitbank-bot
```

That is the application. Default is a **continuous DRY_RUN loop**. On a TTY it
opens the iTerm **取引画面**. HOLD/待機 is normal. Stop with Ctrl-C.
JSON detail is written to `logs/bot.log`.

The launcher never enables LIVE, never checks out a git branch, and forwards
CLI flags:

```bash
./bitbank-bot --screen
./bitbank-bot --once --synthetic --dry-run --skip-lock --no-screen
./bitbank-bot --check-config
```

`--once --synthetic` is a one-cycle smoke test that **exits on purpose**.
`./bitbank-bot` with no extra args does **not** pass `--once`.

`start.sh`, `python3 main.py`, and `python3 run.py` still work.
`main.py` uses the full package when httpx is installed, otherwise the same
stdlib `run.py` (no orders). If pip/venv are missing, `./bitbank-bot` falls
back to `run.py` automatically.

Live trading stays **off** unless `.env` has `TRADING_MODE=live` **and**
`LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK` **and** both API keys.
`DRY_RUN=false` without that confirm phrase is `LIVE_READY` (full path,
`WOULD_SUBMIT_ORDER`, no Bitbank POST). Default remains `DRY_RUN`.


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

- Copy `.env.example` to `.env` is done by `./bitbank-bot` (and `start.sh`) when missing. **Never commit `.env`.**
- If API keys were pasted into chat, **rotate them in the bitbank console**.
- `DRY_RUN=true` and `LIVE_TRADING=true` are mutually exclusive.
- Create `data/KILL` to halt new orders.

## Tests

```bash
./bitbank-bot --once --synthetic --dry-run --skip-lock --no-screen
PYTHONPATH=src .venv/bin/python -m pytest -q
```

Read-only execution check (never places an order):

```bash
python3 scripts/bitbank_execution_audit.py
```

Audit notes: [docs/AUDIT.md](docs/AUDIT.md).

systemd example (not installed by this repo): [deploy/bitbank-bot.service](deploy/bitbank-bot.service).

HTML GitHub wiki exports in the repo root are preserved as-is.
