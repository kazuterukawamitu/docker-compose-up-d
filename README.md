# Bitbank BTC/JPY spot bot

Bitbank-only `btc_jpy` bot. Default is a **continuous DRY_RUN loop** with an iTerm **取引画面** (trading dashboard). HOLD/WAIT on a bar is normal. JSON lines are written to `logs/bot.log`, not the dashboard.

`main` has the DRY_RUN bot. This branch adds `trade.py --live` so the loop starts without pip and can place Bitbank orders.

HOLD for 15 minutes while market data and strategy are healthy is `LONG_WAIT`, not a crash. Public-API fallback candles never place orders. Live UNFILLED limits are persisted and polled. New BUY is blocked when both 4h and 1d SMA slopes are down (`ENABLE_HTF_FILTER`).

## Start (this is the program)

You do **not** need pip, venv, or `httpx`.

Paste **this one line** in iTerm. It starts a 取引画面 and places real Bitbank orders when `.env` has API keys:

```bash
curl -fsSL https://raw.githubusercontent.com/kazuterukawamitu/docker-compose-up-d/cursor/bitbank-trade-live-f5fd/trade.py -o "$HOME/bitbank_trade.py" && python3 "$HOME/bitbank_trade.py" --live
```

From this repo: `python3 trade.py --live` or `bash live.sh`.

- `--live` + `BITBANK_API_KEY` / `BITBANK_API_SECRET` → HMAC `ACCESS-TIME-WINDOW` and `POST /v1/user/spot/order` on a BUY/SELL signal.
- `--live` without keys → the screen still runs (`LIVE_BLOCKED`). Put keys in `.env` (copy `live.env.example`) and restart.
- Without `--live` → paper / public ticker only.

You should see `Bitbank  BTC/JPY  自動売買  取引画面`. HOLD/待機 means no setup — that is not a crash. Stop with Ctrl-C.

Paper-only (never orders): `python3 run.py`.

## Live orders (real Bitbank trades)

`run.py` never calls `create_order`. `trade.py --live` and `live.sh` do.

1. Check out this branch (or run the one-liner below).
2. Copy `live.env.example` to `.env`.
3. Put **your** Bitbank API key and secret in `.env` (trade permission). Do not paste them into chat.
4. Confirm `.env` has `DRY_RUN=false` and `LIVE_TRADING=true` for the full package path.
5. Start:

```bash
bash live.sh
```

Or this one line in iTerm:

```bash
bash -lc 'REPO="$HOME/docker-compose-up-d"; set -euo pipefail; if [ ! -d "$REPO/.git" ]; then git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git "$REPO"; fi; cd "$REPO"; git fetch origin cursor/bitbank-trade-live-f5fd; git checkout -B cursor/bitbank-trade-live-f5fd origin/cursor/bitbank-trade-live-f5fd; exec bash ./live.sh'
```

`live.sh` uses `main.py --require-live` only when venv + httpx + keys + both live flags are already ready. Otherwise it starts `python3 trade.py --live` immediately so the screen is not blocked by pip.

On a signal it sizes from Bitbank `free_amount` (min 0.0001 BTC) and calls `POST /v1/user/spot/order`. HOLD/待機 still means no setup.

If keys were pasted into chat, rotate them first. Touch `data/KILL` to halt new orders.

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
