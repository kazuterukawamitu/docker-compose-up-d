# Bitbank BTC/JPY spot bot

Bitbank-only `btc_jpy` bot. Default is a **continuous DRY_RUN loop** with an iTerm **取引画面**. HOLD/WAIT on a bar is normal. JSON lines go to `logs/bot.log`.

Runnable branch: `cursor/sell-live-complete-d0e4` (`main` is still wiki HTML).

## Five production patches (SELL path)

| Patch | Fix |
| --- | --- |
| 1 Intra-bar exits | STOP / TP follow live price each poll and send **market** sell (no closed-candle wait) |
| 2 Cancel clears pending | `CANCELED_*` releases `state.pending` so the next signal is not blocked |
| 3 Partial-fill slice | New fill size is booked at slice notional, not cumulative average |
| 4 Fee-aware PnL | Realized JPY subtracts quote fees (trade history or `TAKER_FEE_RATE`) |
| 5 Startup reconcile | Live mode matches balances / open orders / trade history on boot |

Also: stale sell limits → market after `SELL_UNFILLED_SEC`; BUY blocked when TP cannot clear round-trip fees (Shannon entropy widens the edge); Granville SELL1–4 coexist with daily-PnL flatten.

## Start (one paste — 超高速)

iTerm にこの **1行** だけ貼る（DRY_RUN・実注文なし）:

```bash
bash -lc 'REPO="$HOME/docker-compose-up-d"; set -euo pipefail; if [ ! -d "$REPO/.git" ]; then git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git "$REPO"; fi; cd "$REPO"; git fetch origin cursor/sell-live-complete-d0e4; git checkout -B cursor/sell-live-complete-d0e4 origin/cursor/sell-live-complete-d0e4; exec bash ./start.sh --screen'
```

stdlib のみの画面（pip 不要）:

```bash
curl -fsSL https://raw.githubusercontent.com/kazuterukawamitu/docker-compose-up-d/cursor/sell-live-complete-d0e4/run.py -o "$HOME/bitbank_run.py" && python3 "$HOME/bitbank_run.py"
```

Checkout 済みなら:

```bash
python3 run.py
# or
bash ./start.sh --screen
```

Live は `.env` で `DRY_RUN=false` **かつ** `LIVE_TRADING=true` **かつ** API keys が揃うまで **絶対に** 発注しません。

## V31 / OOS 同時稼働

- Production: `Strategy`（または安全な `v31.py` プラグイン）
- Shadow: `strategy_shadow`（または `oos.py`）— **発注しない**
- `python3 -m bitbank_bot --audit` で全ギャップ検出（ちゃんプロ型の一括バグ検査）

## Docker / さくら VPS

```bash
# 監査エージェント（注文なし・秘密なし）
docker compose -f docker/compose.audit.yml up --build

# Bot（.env の DRY_RUN を尊重。既定は DRY_RUN）
bash deploy/sakura-vps.sh
# or
docker compose up -d --build
```

systemd 例: [deploy/bitbank-bot.service](deploy/bitbank-bot.service)

## Strategy

State-machine mapping: [docs/STRATEGY.md](docs/STRATEGY.md). Audit notes: [docs/AUDIT.md](docs/AUDIT.md).

## Tests / audit

```bash
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 -m bitbank_bot --audit
python3 scripts/bitbank_execution_audit.py   # read-only Bitbank snapshot
python3 scripts/quality_pipeline.py
```

## Security

- Never commit `.env`. Rotate keys if they were pasted into chat.
- `data/KILL` blocks new buys and sells.
- This repo does **not** SSH into your VPS or turn LIVE on for you.
