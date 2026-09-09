# Bitbank BTC/JPY spot bot

Bitbank-only `btc_jpy` bot. Default is a **continuous DRY_RUN loop** with an iTerm **取引画面** (trading dashboard). HOLD/WAIT on a bar is normal. JSON lines are written to `logs/bot.log`, not the dashboard.

`main` on GitHub is still wiki HTML. The runnable bot is this checkout (`src/bitbank_bot/`).

HOLD for 15 minutes while market data and strategy are healthy is `LONG_WAIT`, not a crash. Public-API fallback candles never place orders. Live UNFILLED limits are persisted and polled. New BUY is blocked when both 4h and 1d SMA slopes are down (`ENABLE_HTF_FILTER`).

## Start (paste this ONE line in iTerm)

iTerm / iTerm2 / iTerm15 opens in your **home directory** (`~`).
`./bitbank-bot` is not in `~`, so zsh prints `no such file or directory`.
A long `bash -lc` line also breaks when iTerm wraps the paste.

Paste **this one line** only. It works from `~`. It needs `curl` and `python3`.

```bash
curl -fsSL https://raw.githubusercontent.com/kazuterukawamitu/docker-compose-up-d/cursor/closed-loop-runtime-hardening/iterm15 -o "$HOME/iterm15" && python3 "$HOME/iterm15"
```

That saves the DRY_RUN program to `~/iterm15` and starts the 取引画面.
HOLD/待機 is normal. Stop with Ctrl-C. No Bitbank order is sent.

Next time, from any directory including `~`:

```bash
python3 "$HOME/iterm15"
```

`--once --synthetic` is a smoke test that **exits on purpose**. Do not add it
to the iTerm start line.

After the repo exists, the full package (still DRY_RUN by default) is:

```bash
bash "$HOME/docker-compose-up-d/scripts/iterm-launch.sh" --screen
```

`./bitbank-bot` only works after `cd` into that folder. Do not type it from `~`.

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
python3 "$HOME/iterm15" --once --synthetic --no-screen
PYTHONPATH=src .venv/bin/python -m pytest -q
```

Read-only execution check (never places an order):

```bash
python3 scripts/bitbank_execution_audit.py
```

Audit notes: [docs/AUDIT.md](docs/AUDIT.md).

systemd example (not installed by this repo): [deploy/bitbank-bot.service](deploy/bitbank-bot.service).

HTML GitHub wiki exports in the repo root are preserved as-is.
