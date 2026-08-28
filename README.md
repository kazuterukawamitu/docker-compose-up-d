# Bitbank BTC/JPY bot

Lightweight spot bot for **Bitbank `btc_jpy`**. It implements the moving-average rules in this repository’s original README. Default mode is **dry-run**: signals are evaluated and fills are simulated. Live `POST /v1/user/spot/order` calls happen only when `DRY_RUN=false` and API keys are set in the environment.

This repository previously contained wiki HTML dumps and strategy notes only. There was no runnable trading code; this package is a new implementation of those notes.

## Strategy (canonical)

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

Defaults used to make those rules executable:

- Pair: `btc_jpy` (shown as BTC/JPY)
- Primary MA: EMA(20) on `5min` candles (`MA_KIND`, `MA_PERIOD`, `CANDLE_TYPE` are configurable)
- Golden cross: EMA(20) above EMA(50)
- 「可能量」: set `ORDER_SIZE_MODE=max_available`. The safer default is `min_unit` (0.0001 BTC).

## Setup

These files live **inside the git repository**. If iTerm shows `~` as the current directory, `requirements.txt` and `bitbank_bot` will not exist there. Clone first, then `cd` into the repo (or call `start.sh` by its full path).

```bash
git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git
cd docker-compose-up-d
# until this branch is merged:
git checkout cursor/bitbank-btc-jpy-bot-fbe5
```

Python **3.12+** is required. macOS CommandLineTools (`/usr/bin/python3`, pip 21.x) is often 3.9 and cannot run this bot. Install a current interpreter, then use the launcher:

```bash
brew install python@3.12
chmod +x start.sh
./start.sh --preflight
./start.sh
```

`start.sh` creates `.venv`, installs dependencies with `python -m pip` (not the missing `pip` command), copies `.env.example` → `.env` if needed, and starts the bot. You can also run it from home:

```bash
~/docker-compose-up-d/start.sh --preflight
~/docker-compose-up-d/start.sh
```

Manual equivalent after `cd` into the repo:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e .
cp .env.example .env
python run.py --preflight
python run.py
```

Do not run `pip3 install -r requirements.txt` from `~`. Do not use system `pip`; that command is often missing. Use `python -m pip` inside `.venv`.

Required for **live** trading only:

- `BITBANK_API_KEY`
- `BITBANK_API_SECRET`

Keys are read from the environment / `.env`. They are never logged.

### iTerm / local start

Preferred:

```bash
cd docker-compose-up-d
./start.sh --preflight
./start.sh
```

Equivalent after the venv is installed:

```bash
cd docker-compose-up-d
source .venv/bin/activate
python run.py --preflight
python run.py
```

Single evaluation cycle (useful in CI):

```bash
python3 -m bitbank_bot --once
```

Backtest a CSV with columns `ts,open,high,low,close,volume`:

```bash
python3 -m bitbank_bot --backtest path/to/candles.csv
```

## Safety

- `DRY_RUN=true` by default. Dry-run does **not** send private order requests.
- Kill switch: `KILL_SWITCH=true` or create `state/KILL`.
- Stale ticker data, daily/total loss caps, max position, duplicate in-flight orders, and Bitbank circuit-break mode all block new orders.
- Market orders are not sent when circuit-break mode is not `NONE`.
- One process at a time per `STATE_DIR` (file lock).

If API keys were ever pasted into chat, tickets, or git history, rotate them on Bitbank before enabling live trading.

## Docker

```bash
docker compose -f deploy/docker-compose.yml up --build
```

## systemd

See `deploy/bitbank-bot.service`. Point `WorkingDirectory` at an install that contains `src/` and a local `.env`.

## Tests

```bash
python -m pytest tests -m "not network"
python -m pytest tests/test_public_api.py -m network
```

Public tests hit `https://public.bitbank.cc` only. They never place orders.
