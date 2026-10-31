# Bitbank BTC/JPY spot bot

Bitbank-only `btc_jpy` bot. Default is a **continuous DRY_RUN loop** with an iTerm **取引画面**. HOLD/WAIT on a bar is normal. JSON lines go to `logs/bot.log`.

Production five patches (always on in patch mode boot log):

1. Intra-bar STOP / take-profit from the public last price (SELL no longer waits for the next 1h close)
2. Cancelled orders clear `pending` (including partial-then-cancel)
3. Partial-fill cost uses incremental notional, not cum-avg × delta
4. Realized PnL deducts quote fees (trade history or `TAKER_FEE_RATE`)
5. Live startup reconciles assets + active orders (including open **sells**)

Also: Shannon entropy fee-edge gate, daily PnL flatten coexisting with Granville BUY/SELL, quantum-inspired adaptive layer, V31 production + OOS shadow (OOS never orders), optional Sentry, Docker verify agent.

`bitbank_bot.config` / `rest_client` / `main` / `watchdog` live under `src/bitbank_bot/`. Always run with `PYTHONPATH=src` or `bash start.sh` (sets it). A bare `import bitbank_bot` from `$HOME` fails if that path is missing.

## Start (paste one line — ultra fast)

Full package on Mac (recommended; DRY_RUN 取引画面):

```bash
curl -fsSL https://raw.githubusercontent.com/kazuterukawamitu/docker-compose-up-d/cursor/bitbank-live-complete-d4a7/scripts/mac_one_paste.sh | bash
```

Stdlib-only fallback (no pip, never live):

```bash
curl -fsSL https://raw.githubusercontent.com/kazuterukawamitu/docker-compose-up-d/cursor/bitbank-live-complete-d4a7/run.py -o "$HOME/bitbank_run.py" && python3 "$HOME/bitbank_run.py"
```

Checked-out repo:

```bash
bash paste.sh                 # prefers full package; falls back to run.py
bash start.sh --screen        # full package
python3 run.py                # stdlib DRY_RUN only
```

You should see `Bitbank  BTC/JPY  取引画面` with 日時損益 and エントロピー. HOLD/待機 is normal when there is no Granville setup. BUY4 now fires on **DOWN or FLAT** dips (default 1%, was 5% DOWN-only). Stop with Ctrl-C.

Audit artifacts: [docs/audit_artifacts/REQUIREMENTS_MATRIX.md](docs/audit_artifacts/REQUIREMENTS_MATRIX.md).

## Unlock LIVE + Sakura VPS

```bash
cp .env.example .env
# set BITBANK_API_KEY / BITBANK_API_SECRET
bash scripts/enable_live.sh          # DRY_RUN=false LIVE_TRADING=true TRADING_MODE=LIVE
PYTHONPATH=src python3 -m bitbank_bot --check-config   # expect LIVE_ALLOWED=true
bash scripts/vps_deploy.sh           # docker compose + verify agents (on VPS)
# or: ENABLE_LIVE=1 bash scripts/vps_deploy.sh
```

Shadow/guard timers become **active** only while `run_forever` is looping. Private API / LIVE order flags become YES only with keys + dual confirm — they are not forced YES in DRY_RUN.

Live trading stays **off** unless `.env` has `DRY_RUN=false` **and** `LIVE_TRADING=true` **and** both API keys (or `TRADING_MODE=LIVE` with keys when the dual flags are unset).

## Gap / bug agents (chan-pro style)

```bash
python3 scripts/gap_agent.py          # purpose vs package
python3 scripts/bug_scan.py           # one finding per anti-pattern hit
python3 scripts/purpose_index.py --search SELL
bash scripts/parallel_agents.sh       # parallel scanners
python3 scripts/bitbank_execution_audit.py
```

## Sentry (optional)

Put the DSN in `.env` as `SENTRY_DSN=...` — do **not** paste Python `import` lines into zsh (that is why you saw `command not found: import` / `bad pattern`).

```bash
# correct checks (Python, not zsh)
export SENTRY_DSN='https://…@….ingest.sentry.io/…'
python3 scripts/sentry_from_env.py
# or
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
