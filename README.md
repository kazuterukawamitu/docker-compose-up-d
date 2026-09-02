# Bitbank BTC/JPY spot bot

Bitbank-only `btc_jpy` bot. Default is a **continuous DRY_RUN loop** (paper signals, **no live orders**). HOLD/WAIT on a bar is normal — the process keeps running.

## Start (paste this ONE line in iTerm)

```bash
bash ~/docker-compose-up-d/start.sh
```

Do **not** paste a stack of commands. Do **not** run `python3 main.py` with macOS system Python (that causes `ModuleNotFoundError: dotenv`). `start.sh` cds into the clone, creates `.venv`, installs deps, copies `.env.example` → `.env` if needed, then starts the loop with `.venv/bin/python`.

Stop with Ctrl-C.

`--once --synthetic` is a one-cycle smoke test that **exits on purpose**. The launcher above does **not** use `--once`.

Live trading stays **off** unless `.env` has `DRY_RUN=false` **and** `LIVE_TRADING=true` **and** both API keys.

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

systemd example (not installed by this repo): [deploy/bitbank-bot.service](deploy/bitbank-bot.service).

HTML GitHub wiki exports in the repo root are preserved as-is.
