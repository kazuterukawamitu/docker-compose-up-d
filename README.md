# Bitbank BTC/JPY spot bot

Bitbank-only `btc_jpy` bot. Default is a **continuous DRY_RUN loop** with an iTerm **取引画面** (trading dashboard). HOLD/WAIT on a bar is normal. JSON lines are written to `logs/bot.log`, not the dashboard.

`main` on GitHub is still mostly wiki HTML plus an older launcher. The
runnable bot on this PR is branch `cursor/bitbank-closed-loop-f964`.

HOLD for 15 minutes while market data and strategy are healthy is `LONG_WAIT`, not a crash. Public-API fallback candles never place orders. Live UNFILLED limits are persisted and polled. New BUY is blocked when both 4h and 1d SMA slopes are down (`ENABLE_HTF_FILTER`).

## Start (this is the program)

The only command to launch the enhanced program. **You MUST `cd` into the
clone first.** Your Mac home `~` is not the repo. `start.sh` exists only
inside the checkout, on branch `cursor/bitbank-closed-loop-f964` (this PR).

```bash
cd ~/docker-compose-up-d
git fetch origin cursor/bitbank-closed-loop-f964
git checkout cursor/bitbank-closed-loop-f964
git ls-files start.sh    # must print: start.sh
bash ./start.sh
```

`bash ./start.sh --help` prints the same instructions. A thin wrapper is
`bash scripts/run_bot.sh` (also refuses unless cwd is this repo).

### `bash: ./start.sh: No such file or directory`

That message is from **bash**, before any bot code runs. Either:

1. The current directory is `~` / `/tmp` / somewhere else — not the clone, or
2. This checkout is `main` without the PR branch, so the enhanced `start.sh`
   is not what you think (or is missing). Run `git ls-files start.sh`.

Fix:

```bash
cd ~/docker-compose-up-d
git checkout cursor/bitbank-closed-loop-f964
bash ./start.sh
```

Optional: install a **home-safe finder** so `cd ~ && bash ./start.sh` prints
the same "cd to the repo" hint instead of a raw "No such file":

```bash
cd ~/docker-compose-up-d
bash scripts/install_launch_alias.sh
```

That copies `scripts/home_start.sh` to `~/start.sh` and adds a `bitbank-start`
function. The home copy does **not** launch the bot and does **not** run tests.

`bash start.sh` from `~` with no finder on `PATH` is expected to fail — there
is no global `start.sh`.

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

## Tests (not launch)

Do **not** paste a pytest command into iTerm at `~`. That is how
`src` goes missing and a pytest line "appears" as if it were a start step.
Launchers never run the test suite unless you pass `--self-test`.

From the repo only:

```bash
cd ~/docker-compose-up-d
bash scripts/run_tests.sh
```

or `bash ./start.sh --self-test`. Same thing: the script `cd`s to the repo
root before it touches pytest. Do not paste the dots or `N passed` line
back into zsh.

Read-only execution check (never places an order):

```bash
python3 scripts/bitbank_execution_audit.py
```

Audit notes: [docs/AUDIT.md](docs/AUDIT.md).

systemd example (not installed by this repo): [deploy/bitbank-bot.service](deploy/bitbank-bot.service).

HTML GitHub wiki exports in the repo root are preserved as-is.
