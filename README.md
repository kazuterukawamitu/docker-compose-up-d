# Bitbank BTC/JPY spot bot

Bitbank-only `btc_jpy` bot. Default is a **continuous DRY_RUN loop** with an iTerm **取引画面**. HOLD/WAIT on a bar is normal. JSON lines go to `logs/bot.log`.

Production five patches (always on in patch mode boot log):

1. Intra-bar STOP / take-profit from the public last price (SELL no longer waits for the next 1h close)
2. Cancelled orders clear `pending` (including partial-then-cancel)
3. Partial-fill cost uses incremental notional, not cum-avg × delta
4. Realized PnL deducts quote fees (trade history or `TAKER_FEE_RATE`)
5. Live startup reconciles assets + active orders (including open **sells**)

Also: Shannon entropy fee-edge gate, daily PnL flatten coexisting with Granville BUY/SELL, quantum-inspired adaptive layer, optional Sentry, Docker verify agent.

## Start (paste one line — ultra fast)

DRY_RUN 取引画面 only (no Bitbank orders, no pip):

```bash
curl -fsSL https://raw.githubusercontent.com/kazuterukawamitu/docker-compose-up-d/cursor/complete-bot-quantum-sentry-9d40/run.py -o "$HOME/bitbank_run.py" && python3 "$HOME/bitbank_run.py"
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

# verification agent (purpose vs package; no orders)
docker compose --profile verify up -d --build verify-agent gap-agent
docker compose logs -f verify-agent
```

Live trading stays **off** unless `.env` has `DRY_RUN=false` **and** `LIVE_TRADING=true` **and** both API keys.

## Gap / bug agents (chan-pro style)

```bash
python3 scripts/gap_agent.py          # purpose vs package
python3 scripts/bug_scan.py           # one finding per anti-pattern hit
python3 scripts/purpose_index.py --search SELL
bash scripts/parallel_agents.sh       # parallel scanners
python3 scripts/bitbank_execution_audit.py
```

## Sentry (optional)

Put the DSN in `.env` as `SENTRY_DSN=...` — do **not** paste Python `import` lines into zsh (that is why you saw `command not found: import`).

```bash
# correct one-liner check
python3 -c 'import os,sentry_sdk; sentry_sdk.init(dsn=os.environ["SENTRY_DSN"]); print("sentry ok")'
```

## Strategy

Granville / README MA rules decide BUY1–4 and pattern SELL1–4. Daily PnL and Shannon entropy run **with** those rules: entropy widens the fee edge for new buys; daily loss / stop / fee-aware TP can flatten from the live ticker without waiting for the next closed hour. The quantum-inspired layer scores up/down/flat scenarios and advises on HOLD stagnation without forcing trades.

State-machine mapping: [docs/STRATEGY.md](docs/STRATEGY.md). Audit: [docs/AUDIT.md](docs/AUDIT.md).

## Tests / archive (tar.gz, not zip)

```bash
PYTHONPATH=src python3 -m pytest -q
python3 run.py --once --synthetic --no-screen
python3 scripts/gap_agent.py
bash scripts/make_archive.sh              # → .tar.gz
FORMAT=tar.xz bash scripts/make_archive.sh
```

## Security

- Never commit `.env`.
- If API keys were pasted into chat, rotate them in the bitbank console.
- `DRY_RUN=true` and `LIVE_TRADING=true` are mutually exclusive.
- Create `data/KILL` to halt new orders.
