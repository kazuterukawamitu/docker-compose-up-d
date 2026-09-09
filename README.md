# Bitbank BTC/JPY spot bot

Bitbank-only `btc_jpy` bot. Default is a **continuous DRY_RUN loop** with an iTerm **取引画面** (trading dashboard). HOLD/WAIT on a bar is normal. JSON lines are written to `logs/bot.log`, not the dashboard.

`main` on GitHub is still wiki HTML. The runnable bot is this checkout (`src/bitbank_bot/`).

HOLD for 15 minutes while market data and strategy are healthy is `LONG_WAIT`, not a crash. Public-API fallback candles never place orders. Live UNFILLED limits are persisted and polled. New BUY is blocked when both 4h and 1d SMA slopes are down (`ENABLE_HTF_FILTER`).

## Start (paste this ONE line in iTerm)

`./bitbank-bot` only works **after** `cd` into the repo. From `~` it fails with
`zsh: no such file or directory`. Paste **this one line** from any directory
(including home). Do not paste the extra flag examples below.

```bash
bash -lc 'set -euo pipefail; REPO="$HOME/docker-compose-up-d"; if [ ! -d "$REPO/.git" ]; then git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git "$REPO"; fi; cd "$REPO"; if [ ! -f src/bitbank_bot/__init__.py ]; then git fetch origin cursor/closed-loop-runtime-hardening; git checkout -B cursor/closed-loop-runtime-hardening origin/cursor/closed-loop-runtime-hardening; fi; exec bash scripts/iterm-launch.sh --screen'
```

That clones to `~/docker-compose-up-d` if needed, checks out the bot branch only
when `src/bitbank_bot` is missing, then starts a **continuous DRY_RUN** 取引画面.
HOLD/待機 is normal. Stop with Ctrl-C. JSON detail is `logs/bot.log`.

After the repo exists, this shorter line also works from **any** directory:

```bash
bash "$HOME/docker-compose-up-d/scripts/iterm-launch.sh" --screen
```

`./bitbank-bot` is only for a shell that is already inside that folder:

```bash
cd "$HOME/docker-compose-up-d" && ./bitbank-bot --screen
```

Optional flags (use only after the repo path above, not as `./bitbank-bot` from `~`):

```bash
bash "$HOME/docker-compose-up-d/scripts/iterm-launch.sh" --once --synthetic --dry-run --skip-lock --no-screen
bash "$HOME/docker-compose-up-d/scripts/iterm-launch.sh" --check-config
```

`--once --synthetic` is a one-cycle smoke test that **exits on purpose**.
The iTerm one-liner does **not** pass `--once`.

The launcher never enables LIVE. If pip/venv are missing it falls back to
stdlib `run.py` (no orders).

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
bash "$HOME/docker-compose-up-d/scripts/iterm-launch.sh" --once --synthetic --dry-run --skip-lock --no-screen
PYTHONPATH=src .venv/bin/python -m pytest -q
```

Read-only execution check (never places an order):

```bash
python3 scripts/bitbank_execution_audit.py
```

Audit notes: [docs/AUDIT.md](docs/AUDIT.md).

systemd example (not installed by this repo): [deploy/bitbank-bot.service](deploy/bitbank-bot.service).

HTML GitHub wiki exports in the repo root are preserved as-is.
