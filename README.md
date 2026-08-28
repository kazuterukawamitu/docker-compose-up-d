# Bitbank BTC/JPY bot

Lightweight spot bot for **Bitbank `btc_jpy`**. It implements the moving-average rules below. Default mode is **dry-run**: signals are evaluated and fills are simulated. Live `POST /v1/user/spot/order` happens only when `DRY_RUN=false` and API keys are set in a local `.env` (never committed).

This repository’s `main` branch was wiki HTML dumps plus these rules. The Python package lives in `src/bitbank_bot/`.

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

Defaults that make those rules executable:

- Pair: `btc_jpy` (shown as BTC/JPY)
- Primary MA: EMA(20) on `5min` candles (`MA_KIND`, `MA_PERIOD`, `CANDLE_TYPE`)
- Golden cross for rule 2 take-profit: EMA(20) above EMA(50)
- 「可能量」: set `ORDER_SIZE_MODE=max_available`. Safer default is `min_unit` (0.0001 BTC)
- Optional wiki golden-cross buy / dead-cross sell: `WIKI_CROSS_RULES=true` (off by default)

## Start (iTerm / macOS)

Do **not** paste this README or Python source into zsh. History expansion (`!`) and markdown (`#`, `**`) cause `zsh: event not found` and `parse error near`. Run the launcher instead.

Python **3.12+** is required. macOS CommandLineTools (`/usr/bin/python3`) is often 3.9 and cannot run this bot.

```bash
git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git
cd docker-compose-up-d
chmod +x start.sh
./start.sh --preflight
./start.sh
```

`start.sh` creates `.venv`, installs with `python -m pip`, copies `.env.example` → `.env` if needed, and starts the bot. You can invoke it from home by full path:

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

Single evaluation cycle:

```bash
python run.py --once
```

Backtest a CSV with columns `ts,open,high,low,close,volume`:

```bash
python run.py --backtest path/to/candles.csv
```

## Safety

- `DRY_RUN=true` by default. Dry-run does **not** send private order requests.
- Kill switch: `KILL_SWITCH=true` or create `state/KILL`.
- Heartbeat logs `[HEARTBEAT]`. After 15 minutes with no trade, `[WATCHDOG]` is `LONG_WAIT` (conditions not met) or `FAIL` (stale data / strategy never ran / signal never reached OrderManager). A quiet market is not a crash.
- Structured logs: `[SIGNAL]`, `[ORDER_REQUEST]`, `[ORDER_STATUS]`, `[FILL]`. Secrets are redacted.
- Keys are read from the environment / `.env`. They are never logged. Rotate any key that was pasted into chat.

## Tests

```bash
python -m pytest -q -m "not network"
```
