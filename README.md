# Bitbank BTC/JPY spot bot (iTerm15 suite)

Moving-average buy/sell bot for **BTC/JPY on bitbank only**. Default mode is **DRY_RUN** (`ORDER_INTENT` / `SIMULATED_FILL` logs, no live orders).

`iTerm15` is the Mac window used to SSH to the VPS. After systemd install, closing iTerm15 must not stop the bot.

Canonical numbers: [docs/MASTER-POLICY.md](docs/MASTER-POLICY.md). Rule mapping: [docs/STRATEGY.md](docs/STRATEGY.md).

## Start from the clone (not from `~`)

```bash
git clone -b cursor/iterm15-suite-6df5 https://github.com/kazuterukawamitu/docker-compose-up-d.git
cd docker-compose-up-d
bash ./start.sh --preflight
bash ./start.sh --once --synthetic --dry-run
bash ./start.sh
```

Do not `chmod start.sh` from the home directory. Do not paste Python into zsh. macOS `/usr/bin/python3` is often 3.9; this bot needs 3.12+ (`brew install python@3.12`).

Other commands:

```bash
PYTHONPATH=src python3 -m bitbank_bot --check-config
PYTHONPATH=src python3 -m bitbank_bot --audit
PYTHONPATH=src python3 -m bitbank_bot --backtest
scripts/run.sh --once --synthetic --dry-run
```

## VPS (survives iTerm15 / SSH drop)

On Ubuntu LTS, from this clone:

```bash
sudo bash scripts/install-vps.sh
sudo systemctl status bitbank-bot
sudo journalctl -u bitbank-bot -f
```

Unit: [deploy/bitbank-bot.service](deploy/bitbank-bot.service) (`Restart=always`). Edit `/opt/bitbank-bot/.env` on the VPS. The Mac stays monitor-only.

## Security

- Copy `.env.example` to `.env`. **Never commit `.env`.**
- If API keys were pasted into chat, **rotate them in the bitbank console**.
- `DRY_RUN=true` and `LIVE_TRADING=true` are mutually exclusive. Live trading requires keys and `DRY_RUN=false`.
- Create `data/KILL` to halt orders.
- Read-only fill audit: `python -m bitbank_bot --audit`.

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

State-machine mapping (SELL > TAKE_PROFIT > BUY) is in [docs/STRATEGY.md](docs/STRATEGY.md).

## Tests

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
PYTHONPATH=src pytest -q
```

Docker (`TZ: Japan`, `ja_JP.UTF-8`):

```bash
docker compose up -d --build
```

zsh: source `scripts/shell-integration.zsh`. Do not paste Python into zsh.

## Behaviour

| Piece | Detail |
| --- | --- |
| Pair | `btc_jpy` only |
| Auth | ACCESS-TIME-WINDOW HMAC-SHA256 |
| Amounts | `PositionSizer` from `free_amount`; 0.0001 BTC; 1 JPY tick |
| Fills | `[FILL]` only when `executed_amount > 0`; dry-run is `[SIMULATED_FILL]` |
| Watchdog | 15-minute `NORMAL_WAIT` / `LONG_WAIT` / `FAIL` (no `sleep(900)`) |
| Timeframes | 8 TFs fetched for health; primary series is `1hour` |
| `--once` | One cycle then exit; terminal bell on clean success |

HTML GitHub wiki exports in the repo root are preserved as-is.
