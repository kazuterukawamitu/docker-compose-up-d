# Bitbank BTC/JPY spot bot

Bitbank-only `btc_jpy` bot. Default is a **continuous DRY_RUN loop** with an iTerm **取引画面** (trading dashboard). HOLD/WAIT on a bar is normal. JSON lines are written to `logs/bot.log`, not the dashboard.

Start with `python3 launch.py`. HOLD for 15 minutes while market data and strategy are healthy is `LONG_WAIT`, not a crash. Public-API fallback candles never place orders. Live UNFILLED limits are persisted and polled. New BUY is blocked when both 4h and 1d SMA slopes are down (`ENABLE_HTF_FILTER`).

## Start (this is the program)

Do **not** run these from the home folder (`~`). `~/main.py` is often a different app (Sentry). Paste **one line at a time**. Do not paste lines that start with `#`.

First clone (only needed once):

```bash
git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git
```

Then every time:

```bash
cd docker-compose-up-d
```

```bash
bash start.sh
```

`bash start.sh` installs a venv if needed and opens the DRY_RUN 取引画面. You can also run `python3 launch.py` after `cd docker-compose-up-d`.

You should see `Bitbank BTC/JPY 起動プログラム` then `Bitbank  BTC/JPY  取引画面`. HOLD/待機 is normal. Stop with Ctrl-C.

If Apple `python3` is 3.9 (LibreSSL warning), install 3.12 then start with it:

```bash
brew install python@3.12
```

```bash
/opt/homebrew/bin/python3.12 launch.py
```

`python3 run.py` is the stdlib-only DRY_RUN screen (no pip). Do not run `python3 main.py` from `~`.

`python3 launch.py --doctor` prints a safe environment check (no secrets). If you copied `launch.py` to another folder, it looks for `~/docker-compose-up-d` and clones there when missing.

Live trading stays **off** unless `.env` has `TRADING_MODE=live` **and**
`DRY_RUN=false` **and** `LIVE_TRADING=true` **and**
`LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK` **and** both API keys.

Without the confirm phrase, `DRY_RUN=false` + `LIVE_TRADING=true` becomes
**LIVE_READY** (full path, `WOULD_SUBMIT_ORDER`, no `create_order`).

`RATE_MODE=fixed` (default) keeps README take-profits (+3/+4/+5/+8).
`dynamic` / `auto` only scale TP/size from ATR; they do not change entry rules.

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
- Create `data/KILL` to halt new orders.

## Tests

```bash
bash start.sh --once --synthetic --skip-lock
python3 launch.py --once --synthetic --skip-lock --no-screen
PYTHONPATH=src python3 -m pytest -q
```

Read-only execution check (never places an order):

```bash
python3 scripts/bitbank_execution_audit.py
```

Audit notes: [docs/AUDIT.md](docs/AUDIT.md).

systemd example (not installed by this repo): [deploy/bitbank-bot.service](deploy/bitbank-bot.service).

HTML GitHub wiki exports in the repo root are preserved as-is.
