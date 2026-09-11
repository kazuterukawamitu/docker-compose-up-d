# Bitbank BTC/JPY spot bot

Bitbank-only `btc_jpy` bot. Default is a **continuous DRY_RUN loop** with an iTerm **取引画面** (trading dashboard). HOLD/WAIT on a bar is normal. JSON lines are written to `logs/bot.log`, not the dashboard.

`main` on GitHub is still wiki HTML. The runnable bot is branch `cursor/bitbank-audit-unify-f5fd`.

HOLD for 15 minutes while market data and strategy are healthy is `LONG_WAIT`, not a crash. Public-API fallback candles never place orders. Live UNFILLED limits are persisted and polled. New BUY is blocked when both 4h and 1d SMA slopes are down (`ENABLE_HTF_FILTER`).

## Start (this is the program)

The only command to launch the enhanced program. **cd into the repo first**
(your Mac home `~` is not the repo):

```bash
cd ~/docker-compose-up-d   # or wherever you cloned this repository
bash ./start.sh
```

`bash ./start.sh --help` prints the same instructions. A thin wrapper is
`bash scripts/run_bot.sh` (also refuses unless cwd is this repo).

One-cycle dry health check (no orders):

```bash
bash ./start.sh --once --synthetic --skip-lock --no-screen
```

`start.sh` finds this repo from its own path (not a hardcoded Mac home), uses
`.venv`, loads `.env` without printing secrets, and starts the existing
`python -m bitbank_bot` entry. LIVE is refused unless `TRADING_MODE=LIVE` **and**
`LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK` **and** both API keys.
Default remains `DRY_RUN`. JSON logs go to `logs/bot.log` (rotated 5MB × 5).
`data/KILL` halts new orders. `data/bot.lock` is the instance lock.

Same launcher without the shell wrapper:

```bash
PYTHONPATH=src python3 -m bitbank_bot.launch
python3 main.py
```

Stdlib-only fallback (no pip / no venv), still DRY_RUN and no orders:

```bash
python3 run.py
```

`python -m bitbank_bot` is the engine only (no crash-restart wrapper). Use that
under systemd (`deploy/bitbank-bot.service`) or pass `--no-supervise`.

Paste **this one line** in iTerm to clone and open the 取引画面:

```bash
bash -lc 'REPO="$HOME/docker-compose-up-d"; set -euo pipefail; if [ ! -d "$REPO/.git" ]; then git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git "$REPO"; fi; cd "$REPO"; git fetch origin cursor/bitbank-closed-loop-f964; git checkout -B cursor/bitbank-closed-loop-f964 origin/cursor/bitbank-closed-loop-f964; exec bash ./start.sh --screen'
```

HOLD/待機 is normal. Stop with Ctrl-C.

### If you see `zsh: command not found: ....`

That is **not** a bot crash. pytest progress (`.... [ 40%]`) and `179 passed`
were pasted into zsh at `~`. zsh tried to run the dots as commands.

1. If the prompt is a lone `>` (continuation after an unclosed quote), press **Ctrl-C**.
2. Then start the program from the repo:

```bash
cd ~/docker-compose-up-d
bash ./start.sh
```

Do **not** paste pytest output, Python snippets, or chat excerpts into the terminal.

Live trading stays **off** unless `.env` has `TRADING_MODE=LIVE` **and**
`LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK` **and** both API keys.
If either LIVE flag is missing, the bot is `LIVE_READY` (full path except the
order POST; logs `WOULD_SUBMIT_ORDER`). `DRY_RUN=true` remains the default.

`CANDLE_TYPE=5min` is supported (Bitbank `btc_jpy` / `5min` / JST `YYYYMMDD`,
including yesterday near midnight). Accidental synthetic candles never place
orders (`EXECUTION_BLOCKED` / `synthetic_market_data`).

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
bash ./start.sh --once --synthetic --skip-lock --no-screen
PYTHONPATH=src python3 -m pytest -q
```

Run those commands in the repo. Do not paste the pytest dots or `N passed` line
back into zsh.

Read-only execution check (never places an order):

```bash
python3 scripts/bitbank_execution_audit.py
```

Audit notes: [docs/AUDIT.md](docs/AUDIT.md).

systemd example (not installed by this repo): [deploy/bitbank-bot.service](deploy/bitbank-bot.service).

HTML GitHub wiki exports in the repo root are preserved as-is.
