# Bitbank BTC/JPY spot bot

Bitbank-only `btc_jpy` bot. Default is a **continuous DRY_RUN loop** with an iTerm **取引画面**. HOLD/WAIT on a bar is normal. JSON lines go to `logs/bot.log`.

This branch (`cursor/production-five-patches-7ec0`) includes the five production patches:

1. Intra-bar STOP / take-profit from the public last price (SELL no longer waits for the next 1h close)
2. Cancelled orders clear `pending` (including partial-then-cancel)
3. Partial-fill cost uses incremental notional, not cum-avg × delta
4. Realized PnL deducts quote fees (trade history or `TAKER_FEE_RATE`)
5. Live startup reconciles assets + active orders

Plus: Shannon entropy fee-edge gate, daily PnL flatten, Docker image, gap/bug agents.

## Start (paste one line — ultra fast)

DRY_RUN 取引画面 only (no Bitbank orders, no pip):

```bash
curl -fsSL https://raw.githubusercontent.com/kazuterukawamitu/docker-compose-up-d/cursor/production-five-patches-7ec0/run.py -o "$HOME/bitbank_run.py" && python3 "$HOME/bitbank_run.py"
```

Checked-out repo:

```bash
python3 run.py
# or
bash paste.sh
```

You should see `Bitbank  BTC/JPY  取引画面` with 日時損益 and エントロピー. HOLD/待機 is normal when there is no Granville setup. Stop with Ctrl-C.

`python3 main.py` prefers the full package when httpx is installed; otherwise the same stdlib `run.py`.

## Live on Sakura VPS (Docker)

```bash
cp .env.example .env
# set BITBANK_API_KEY / BITBANK_API_SECRET
# DRY_RUN=false
# LIVE_TRADING=true
docker compose up -d --build
docker compose logs -f bitbank-bot
```

Live trading stays **off** unless `.env` has `DRY_RUN=false` **and** `LIVE_TRADING=true` **and** both API keys.

## Gap / bug agents (chan-pro style)

```bash
python3 scripts/gap_agent.py    # purpose vs package (6+ patches)
python3 scripts/bug_scan.py     # one finding per anti-pattern hit
python3 scripts/bitbank_execution_audit.py   # read-only Bitbank snapshot
```

## Origin CLI (laptop)

On a MacBook / local shell:

```bash
curl -fsSL https://downloads.cursor.com/origin/install.sh | sh
origin auth login
origin auth setup-git
```

On a Cursor-hosted cloud agent VM, `origin auth login` is refused — the host injects `CURSOR_AUTH_TOKEN`. Do not try to store a login there.

Docs: https://cursor.com/docs/origin/cli

## Strategy

Granville / README MA rules decide BUY1–4 and pattern SELL1–4. Daily PnL and Shannon entropy run **with** those rules: entropy widens the fee edge for new buys; daily loss / stop / fee-aware TP can flatten from the live ticker without waiting for the next closed hour.

State-machine mapping: [docs/STRATEGY.md](docs/STRATEGY.md). Audit: [docs/AUDIT.md](docs/AUDIT.md).

## Tests

```bash
PYTHONPATH=src python3 -m pytest -q
python3 run.py --once --synthetic --no-screen
python3 scripts/gap_agent.py
```

## Security

- Never commit `.env`.
- If API keys were pasted into chat, rotate them in the bitbank console.
- `DRY_RUN=true` and `LIVE_TRADING=true` are mutually exclusive.
- Create `data/KILL` to halt new orders.
