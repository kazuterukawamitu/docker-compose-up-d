# Bitbank BTC/JPY spot bot

Bitbank-only `btc_jpy` bot. Default is a **continuous DRY_RUN loop** with an iTerm **取引画面** (trading dashboard). HOLD/WAIT on a bar is normal. JSON lines are written to `logs/bot.log`, not the dashboard.

`main` on GitHub is still wiki HTML. The runnable bot is branch `cursor/bitbank-audit-unify-f5fd`.

HOLD for 15 minutes while market data and strategy are healthy is `LONG_WAIT`, not a crash. Public-API fallback candles never place orders. Live UNFILLED limits are persisted and polled. New BUY is blocked when both 4h and 1d SMA slopes are down (`ENABLE_HTF_FILTER`).

## Start (this is the program)

`main` on GitHub is wiki HTML. The runnable bot is on a `cursor/…` branch (see commands below).

### If you see `can't open file '.../main.py'`

iTerm2 opened in your **home folder** (`~` in the prompt). `python3 main.py` then looks for `/Users/<you>/main.py`, which does not exist. `main.py` is inside the cloned repo, not in `~`.

**Wrong** (prompt is `~ %`):

```bash
python3 main.py --once --skip-lock --no-screen
```

**Right** — `cd` into the clone first, or call `start.sh` by full path (both work while the prompt still says `~ %`):

```bash
cd "$HOME/docker-compose-up-d" && bash ./start.sh --screen
```

```bash
bash "$HOME/docker-compose-up-d/start.sh" --screen
```

Find the clone if it is not at `~/docker-compose-up-d`:

```bash
ls "$HOME/docker-compose-up-d/main.py"
find "$HOME" -name main.py -path '*docker-compose-up-d*' 2>/dev/null
```

### Continuous DRY_RUN 取引画面 (normal startup)

This keeps the program running. HOLD/待機 is normal. Stop with Ctrl-C. No live orders.

**Already cloned** at `~/docker-compose-up-d`:

```bash
bash "$HOME/docker-compose-up-d/scripts/iterm2-from-home.sh"
```

**First time on this Mac** (clone if needed, then start):

```bash
bash -lc 'REPO="$HOME/docker-compose-up-d"; set -euo pipefail; if [ ! -d "$REPO/.git" ]; then git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git "$REPO"; fi; cd "$REPO"; git fetch origin cursor/bitbank-closed-loop-execution-dee2; git checkout -B cursor/bitbank-closed-loop-execution-dee2 origin/cursor/bitbank-closed-loop-execution-dee2; exec bash ./start.sh --screen'
```

**No git clone** (stdlib dashboard only; writes `~/bitbank_run.py`):

```bash
curl -fsSL https://raw.githubusercontent.com/kazuterukawamitu/docker-compose-up-d/cursor/bitbank-closed-loop-execution-dee2/run.py -o "$HOME/bitbank_run.py" && python3 "$HOME/bitbank_run.py"
```

You should see `Bitbank  BTC/JPY  取引画面`.

If you are already inside the repo folder (`ls main.py` works):

```bash
python3 run.py
```

`python3 main.py` also works **from that folder**: full package when httpx is installed, otherwise the same stdlib `run.py`.

### One-cycle smoke test (exits on purpose)

Use this only to check that Python can load the bot. It is **not** the normal startup; `--once` exits after one cycle.

```bash
cd "$HOME/docker-compose-up-d" && DRY_RUN=true LIVE_TRADING=false ENABLE_WEBSOCKET=false python3 main.py --once --skip-lock --no-screen
```

Or without `cd`, from `~`:

```bash
DRY_RUN=true LIVE_TRADING=false ENABLE_WEBSOCKET=false bash "$HOME/docker-compose-up-d/start.sh" --once --skip-lock --no-screen
```

Live trading stays **off** unless `.env` has `TRADING_MODE=live` **and**
`LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK` **and** both API keys.
`DRY_RUN=false` without that confirm phrase is `LIVE_READY` (WOULD_SUBMIT_ORDER only).


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
