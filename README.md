# Bitbank BTC/JPY spot bot

`main` on this repository previously had **no Python entrypoint** — only GitHub wiki HTML dumps and a README of moving-average rules. This tree adds a **Bitbank-only** `btc_jpy` bot. Default mode is **DRY_RUN**: signals are evaluated and paper fills are logged; **no live orders**.

## How to start (DRY_RUN)

```bash
cd docker-compose-up-d
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # leave BITBANK_API_KEY / BITBANK_API_SECRET empty
python3 main.py --once --synthetic --dry-run --skip-lock
```

Loop (still DRY_RUN unless you change `.env`):

```bash
python3 main.py --skip-lock
# or
bash ./start.sh --once --synthetic --dry-run --skip-lock
PYTHONPATH=src python3 -m bitbank_bot --check-config
PYTHONPATH=src python3 -m bitbank_bot --preflight
```

Live trading is **off** unless `.env` has `DRY_RUN=false` **and** `LIVE_TRADING=true` **and** both API keys. Do not set those flags unless you intend to send real orders.

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

- Copy `.env.example` to `.env`. **Never commit `.env`.**
- If API keys were pasted into chat, **rotate them in the bitbank console**.
- `DRY_RUN=true` and `LIVE_TRADING=true` are mutually exclusive.
- Create `data/KILL` to halt new orders.

## Tests

```bash
PYTHONPATH=src pytest -q
```

systemd example (not installed by this repo): [deploy/bitbank-bot.service](deploy/bitbank-bot.service).

HTML GitHub wiki exports in the repo root are preserved as-is.
