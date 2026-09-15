# Bitbank BTC/JPY spot bot

Your iTerm prompt is `~` (`/Users/kazuterukawamitsu`). Commands without a
directory run against **home**, not this clone.

- `python3 closed_loop.py` → `/Users/kazuterukawamitsu/closed_loop.py` (file does not exist)
- `python3 /path/to/docker-compose-up-d/closed_loop.py` → that string is a placeholder, not a path
- `python3 main.py` → `/Users/kazuterukawamitsu/main.py` (Sentry, `BadDsn: Unsupported scheme ''`)
- `python3 -m bitbank_bot` → no package in home
- `bash ./start.sh` from `~` → a **home finder** for branch `cursor/closed-loop-launcher-563e`, not this bot

The clone is `~/docker-compose-up-d`. This bot lives on branch
`cursor/bitbank-closed-loop-1114`. `main` has `start.sh` but **not** `closed_loop.py`.

## Launch (paste this from `~`)

One DRY_RUN cycle, then exit. HOLD / `no_buy_setup` is a successful start. No live orders.

```bash
cd ~/docker-compose-up-d && git fetch origin cursor/bitbank-closed-loop-1114 && git checkout -B cursor/bitbank-closed-loop-1114 origin/cursor/bitbank-closed-loop-1114 && bash ./start.sh --go
```

You should see `LAUNCH_OK` and then `run_once complete`. Apple CommandLineTools
`python3` is not used; `start.sh` creates `.venv` and installs `httpx`.

Later starts (clone already on this branch):

```bash
bash ~/docker-compose-up-d/start.sh --go
```

Continuous 取引画面 (Ctrl-C to stop):

```bash
bash ~/docker-compose-up-d/start.sh --screen
```

## What not to paste at `~`

- `python3 closed_loop.py` / `python3 closed_loop.py --go`
- `python3 /path/to/docker-compose-up-d/closed_loop.py --go`
- `python3 main.py` (Sentry)
- `python3 src/bitbank_bot/main.py`
- `python3 -m bitbank_bot`
- `bash ./start.sh` / `bash ./start.sh --go` / `bash ./start.sh --screen`
- pytest output (`.... [ 40%]`) — pytest is not a launch step

The runnable bot is in `src/bitbank_bot/` on branch `cursor/bitbank-closed-loop-1114`. Wiki HTML files in the repo root are leftover chart dumps and are not loaded.

HOLD for 15 minutes while market data and strategy are healthy is `LONG_WAIT`, not a crash. Public-API fallback candles never place orders. Live UNFILLED limits are persisted and polled. New BUY is blocked when both 4h and 1d SMA slopes are down (`ENABLE_HTF_FILTER`).

## Checks

```bash
bash ~/docker-compose-up-d/start.sh --help
python3 ~/docker-compose-up-d/closed_loop.py --review
python3 ~/docker-compose-up-d/closed_loop.py --verify --no-public
```

Live trading stays **off** unless `.env` has `DRY_RUN=false` **and** `LIVE_TRADING=true` **and** both API keys **and** `LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK`. Missing the confirm phrase stays in `LIVE_READY` (`WOULD_SUBMIT_ORDER` only). Default `RATE_MODE=fixed` keeps the README take-profit percents.

Bitbank’s public “today” candlestick file can 404 at JST midnight (code 10000). Incremental fetch also loads yesterday, and the loop keeps cached real bars instead of switching to synthetic no-orders. HOLD / `no_buy_setup` is a valid Granville miss; `BUY_GATE` logs which checks failed.

Contradiction resolution: [MASTER_REQUIREMENTS.md](MASTER_REQUIREMENTS.md). Evidence: [COMPLETION_MATRIX.md](COMPLETION_MATRIX.md).

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

Run tests from the clone, not from `~`:

```bash
cd ~/docker-compose-up-d
PYTHONPATH=src python3 -m pytest -q
```

Read-only execution check (never places an order):

```bash
python3 ~/docker-compose-up-d/scripts/bitbank_execution_audit.py
```

Audit notes: [docs/AUDIT.md](docs/AUDIT.md).

systemd example (not installed by this repo): [deploy/bitbank-bot.service](deploy/bitbank-bot.service).

HTML GitHub wiki exports in the repo root are preserved as-is.
