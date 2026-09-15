# Bitbank BTC/JPY spot bot

Bitbank-only `btc_jpy` bot. Default is a **continuous DRY_RUN loop** with an iTerm **取引画面** (trading dashboard). HOLD/WAIT on a bar is normal. JSON lines are written to `logs/bot.log`, not the dashboard.

`main` on GitHub is still mostly wiki HTML plus an older launcher. The
runnable bot on this PR is branch `cursor/bitbank-closed-loop-f964`.

HOLD for 15 minutes while market data and strategy are healthy is `LONG_WAIT`, not a crash. Public-API fallback candles never place orders. Live UNFILLED limits are persisted and polled. New BUY is blocked when both 4h and 1d SMA slopes are down (`ENABLE_HTF_FILTER`).

## Start (this is the program)

Do **not** paste this chat, JSON logs, agent reports, or script source into
iTerm. Never `bash /workspace/start.sh` (cloud VM). Never `~/.venv`.
Branch `cursor/bitbank-closed-loop-f964`. Launchers `cd` via `BASH_SOURCE`
and run **`$ROOT/.venv/bin/python` only**.

### Paper transaction (copy this ONE line)

From `~` on a Mac this finds `~/docker-compose-up-d`, uses the repo `.venv`,
and completes a DRY_RUN paper fill (`LAUNCH_OK`, `ORDER_INTENT`,
`SIMULATED_FILL`, `SMOKE_ORDER_OK`). Bitbank is **not** POSTed.

```bash
bash ~/docker-compose-up-d/run_transaction.sh
```

If the clone exists but may be on the wrong branch, this is still one line:

```bash
bash -lc 'cd "$HOME/docker-compose-up-d" && git fetch origin cursor/bitbank-closed-loop-f964 && git checkout cursor/bitbank-closed-loop-f964 && exec bash ./run_transaction.sh'
```

Success looks like `LAUNCH_OK ... mode=DRY_RUN live=false` then
`SMOKE_ORDER_OK` / `SIMULATED_FILL` with `create_order_called=false`.
That is a paper transaction, not HOLD.

### Continuous 取引画面 (HOLD is normal)

This is the looping dashboard. HOLD / `no_buy_setup` on a bar is **not** a
failed transaction. Stop with Ctrl-C.

```bash
bash ~/docker-compose-up-d/start.sh
```

Apple `/usr/bin/python3` (Xcode CommandLineTools) must not be aimed at a
random file while your cwd is `~` — that is
`can't open file ... [Errno 2]` (`python3 test_public.py`,
`python3 main.py`, `/Users/.../test_public.py`). `pytest` from `~` is
`no tests ran`.

```bash
cd ~/docker-compose-up-d
git fetch origin cursor/bitbank-closed-loop-f964
git checkout cursor/bitbank-closed-loop-f964
git ls-files start.sh    # must print: start.sh
bash ./start.sh
```

`bash ./start.sh --help` prints the same instructions.
`python launch_bot.py --execute --smoke-order` from the clone forwards to
the same paper path. Tests:
`bash ~/docker-compose-up-d/scripts/run_tests.sh` (not `pytest` from `~`).

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
# or: bash ~/docker-compose-up-d/start.sh
```

Optional: install a **home-safe finder** so `cd ~ && bash ./start.sh` prints
the same "cd to the repo" hint instead of a raw "No such file":

```bash
cd ~/docker-compose-up-d
bash scripts/install_launch_alias.sh
```

That copies `scripts/home_start.sh` to `~/start.sh` and adds a `bitbank-start`
function. The home copy does **not** launch the bot and does **not** run tests.

`bash start.sh` or `./start.sh` from `~` with no finder on `PATH` is expected
to fail — there is no global `start.sh`. Use the absolute path shown above.

One-cycle dry health check (no orders):

```bash
bash ./start.sh --once --synthetic --skip-lock --no-screen
```

`start.sh` finds this repo from its own path (not a hardcoded Mac home), uses
the repo `.venv` only (never `~/.venv`), loads `.env` without printing secrets,
and starts the existing `python -m bitbank_bot` entry. LIVE is refused unless `TRADING_MODE=LIVE` **and**
`LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK` **and** both API keys.
Default remains `DRY_RUN`. JSON logs go to `logs/bot.log` (rotated 5MB × 5).
`data/KILL` halts new orders. `data/bot.lock` is the instance lock.

Same launcher without the shell wrapper (still from the clone; still not `~/.venv`):

```bash
python3 launch_bot.py
PYTHONPATH=src python3 -m bitbank_bot.launch
python3 main.py
```

Stdlib-only fallback (no pip / no venv), still DRY_RUN and no orders:

```bash
python3 run.py
```

`python -m bitbank_bot.launch --no-supervise --no-screen` is the systemd
entry (`deploy/bitbank-bot.service`, `Restart=always`). That is the same
stack as `start.sh`, without a nested restart loop. `python -m bitbank_bot`
is Engine-only.

Print the start graph without starting Engine (no orders):

```bash
bash ~/docker-compose-up-d/start.sh --print-plan
```

Paste **this one line** in iTerm to clone and open the 取引画面:

```bash
bash -lc 'REPO="$HOME/docker-compose-up-d"; set -euo pipefail; if [ ! -d "$REPO/.git" ]; then git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git "$REPO"; fi; cd "$REPO"; git fetch origin cursor/bitbank-closed-loop-f964; git checkout -B cursor/bitbank-closed-loop-f964 origin/cursor/bitbank-closed-loop-f964; exec bash ./start.sh --screen'
```

HOLD/待機 is normal. Stop with Ctrl-C.

### If you see `zsh: command not found: ts:` / `SMOKE_ORDER_OK` / `....`

That is **not** a bot crash. JSON bot logs (`"ts":`, `SMOKE_ORDER_OK`,
`FAILURE`, `compileall:`, `HOW`, `LIVE`), pytest progress (`.... [ 40%]`),
or an agent report were pasted into zsh at `~`. zsh tried to run those tokens
as commands. `zsh: event not found` means a shebang bang was pasted (do not
paste `start.sh` source). `bash: /workspace/start.sh: No such file` is the
cloud VM path, not a Mac path.

1. If the prompt is a lone `>` (continuation after an unclosed quote), press **Ctrl-C**.
2. Then run ONE of:

```bash
bash ~/docker-compose-up-d/run_transaction.sh
bash ~/docker-compose-up-d/start.sh
```

Do **not** paste JSON logs, agent reports, pytest output, Python snippets, or
script source into the terminal. Never `~/.venv`.

Live trading stays **off** unless `.env` has `TRADING_MODE=LIVE` **and**
`LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK` **and** both API keys.
If either LIVE flag is missing, the bot is `LIVE_READY` (full path except the
order POST; logs `WOULD_SUBMIT_ORDER`). `DRY_RUN=true` remains the default.

`CANDLE_TYPE=5min` is supported (Bitbank `btc_jpy` / `5min` / JST `YYYYMMDD`,
including yesterday near midnight). Accidental synthetic candles never place
orders (`EXECUTION_BLOCKED` / `synthetic_market_data`).

`run_transaction.sh` is the paper-fill path (`--execute --smoke-order`). It is
not `--once` strategy HOLD. Default `bash ./start.sh` is the continuous loop
and does **not** inject `--once` or `--execute`.

`--once --synthetic` remains a one-cycle health check that **exits on purpose**.


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

From any cwd (the script `cd`s to the repo; do not run `pytest` from `~`):

```bash
cd ~/docker-compose-up-d
bash scripts/run_tests.sh
# or: bash ~/docker-compose-up-d/scripts/run_tests.sh
```

or `bash ./start.sh --self-test`. Do not paste the dots or `N passed` line
back into zsh.

Read-only execution check (never places an order):

```bash
python3 scripts/bitbank_execution_audit.py
```

Audit notes: [docs/AUDIT.md](docs/AUDIT.md).

systemd example (not installed by this repo): [deploy/bitbank-bot.service](deploy/bitbank-bot.service).

HTML GitHub wiki exports in the repo root are preserved as-is.
