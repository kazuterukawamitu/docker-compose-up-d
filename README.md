# Bitbank BTC/JPY spot bot

Moving-average buy/sell bot for **BTC/JPY on bitbank only**. Default mode is **DRY_RUN** (`ORDER_INTENT` logs, no live orders).

Startup:

```bash
PYTHONPATH=src python3 -m bitbank_bot --once
```

Other commands:

```bash
PYTHONPATH=src python3 -m bitbank_bot --preflight
PYTHONPATH=src python3 -m bitbank_bot --dry-run
PYTHONPATH=src python3 -m bitbank_bot
scripts/run.sh --once
```

## Security

- Copy `.env.example` to `.env`. **Never commit `.env`.**
- If API keys were pasted into chat or a ticket, **rotate them in the bitbank console** and treat the old pair as compromised.
- `DRY_RUN=true` and `LIVE_TRADING=true` are mutually exclusive. Live trading requires keys and `DRY_RUN=false`.
- Create `data/KILL` to halt orders (kill switch).

## Strategy

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

State-machine mapping (SELL > TAKE_PROFIT > BUY; no SELL on the entry candle) is in [docs/strategy.md](docs/strategy.md).

## Setup

Python 3.12+:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
PYTHONPATH=src python3 -m bitbank_bot --preflight
```

Tests:

```bash
PYTHONPATH=src pytest -q
```

Docker (locale `ja_JP.UTF-8`, `TZ: Japan` as in the original compose snippet):

```bash
docker compose up -d --build
```

systemd unit: [deploy/bitbank-bot.service](deploy/bitbank-bot.service).

zsh: source `scripts/shell-integration.zsh` (`HIST_VERIFY`, venv `PATH`). Do not paste Python into zsh.

## Behaviour

| Piece | Detail |
| --- | --- |
| Pair | `btc_jpy` only |
| Auth | ACCESS-TIME-WINDOW HMAC-SHA256 matching python-bitbankcc |
| Public REST | `https://public.bitbank.cc` |
| Private REST | `https://api.bitbank.cc/v1` |
| WebSocket | `wss://stream.bitbank.cc/socket.io/?EIO=4&transport=websocket` rooms `ticker_`, `transactions_`, `depth_whole_` |
| Amounts | Recalculated from `free_amount` every order; BTC floored to 0.0001; JPY tick 1; exchange min/max honored |
| Watchdog | 15-minute `LONG_WAIT` (no signal) vs `FAIL` (stuck loop) |
| `--once` | One cycle then exit; terminal bell on clean success |

HTML GitHub wiki exports in the repo root are preserved as-is.
