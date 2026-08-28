# Bitbank BTC/JPY trading bot

Automated **Bitbank-only** spot bot for `btc_jpy` (display: **BTC/JPY**). Python 3.12, asyncio, dry-run by default.

This repository previously held wiki HTML dumps and a stub GitHub Action. The bot is a new, small Python package. It does **not** place live orders unless you set `DRY_RUN=false` and provide API keys in a local `.env` file.

## Safety

- Default `DRY_RUN=true`. Public market data is fetched; intended orders are logged and simulated. `POST /v1/user/spot/order` is not called.
- Never commit `.env` or API secrets. `.env.example` is a template only.
- Pair is locked to `btc_jpy`. Minimum size is **0.0001 BTC**. Price tick is **1 JPY**.
- Live mode requires `BITBANK_API_KEY` and `BITBANK_API_SECRET`. After a live `POST` timeout the bot does **not** retry that order (unknown fill).
- No profit is guaranteed. Circuit-breaker / itayose (`circuit_break_info.mode != NONE`) blocks live orders.

## Trading rules (README spec)

These are the original Japanese rules encoded in `GranvilleStrategy`:

```
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
```

Buy sizing uses free JPY minus fee and safety margin, quantized down to 0.0001 BTC. Sell sizing uses free BTC (all). Risk manager can flatten on stop-loss, trailing stop, take-profit cap, or max-loss.

Optional extra strategies (`golden_cross`, `death_cross`, `rsi`, `macd`, `atr_breakout`) can be listed in `STRATEGIES` but default is `granville` only.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env`. Leave `DRY_RUN=true` until you intend live trading.

```bash
python -m bitbank_bot preflight
python -m bitbank_bot run
python -m bitbank_bot backtest tests/fixtures/sample_ohlcv.csv
pytest
```

`preflight` checks the public Bitbank API (ticker, depth, candles, circuit breaker). In live mode it also reads balances. It never places orders.

## Docker

```bash
cp .env.example .env
docker compose -f deploy/docker-compose.yml up --build
```

The image sets `TZ=Asia/Tokyo` and `ja_JP.UTF-8` (from the original locale snippet in this repo). Compose still forces `DRY_RUN=true`.

## systemd (VPS)

Copy `deploy/bitbank-bot.service` to `/etc/systemd/system/`, point `WorkingDirectory` at the checkout, keep `DRY_RUN=true` in the unit or `.env`, then `systemctl enable --now bitbank-bot`.

## Layout

```
src/bitbank_bot/     package (config, REST/WS, indicators, strategy, risk, orders)
tests/               pytest (no live orders)
deploy/              Dockerfile, compose, systemd unit
```

Bitbank docs used for signing and endpoints: https://github.com/bitbankinc/bitbank-api-docs
