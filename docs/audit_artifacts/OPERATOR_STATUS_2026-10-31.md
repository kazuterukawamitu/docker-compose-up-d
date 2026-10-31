# Operator status — 2026-10-31 (Asia/Tokyo)

## What was verified on this cloud agent

| Check | Result | Evidence |
| --- | --- | --- |
| Package modules `config` / `rest_client` / `main` / `watchdog` | present | `src/bitbank_bot/*.py` |
| pytest | PASS | 159 tests |
| `gap_agent.py` | ALL PASS | SELL_INTRABAR … TRADING_MODE |
| `bug_scan.py` | 0 findings | — |
| Bitbank **public** API | OK | ticker last ≈ 12,201,871; 1h candles loaded |
| Strategy on live candles | HOLD / `no_buy_setup` | price above FLAT MA (~0.2%); wait for cross-down or dip |
| V31 + OOS dual | wired | OOS `execute=false` |
| shadow/guard timers | inactive in `--once` | become active only inside `run_forever` |
| Private API / LIVE / order_create | NO | no keys in this environment (`BLOCK_REASON=dry_run`) |
| SSH `rocky@49.212.212.148` | **Permission denied** (publickey) | cannot prove VPS source hash from here |
| Docker on this VM | **not installed** | use `scripts/vps_deploy.sh` / compose on VPS or Mac |

## Mac screen you pasted

- DRY_RUN, cycles≈14000+, FLAT, HOLD/`no_buy_setup`, 建玉なし — **expected** while price is above the MA and gates are dry-run.
- Footer「このプログラムは注文しません」 matches an **older** screen string; current package explains DRY_RUN + `enable_live.sh`.
- Re-pull feature branch before judging BUY scarcity:

```bash
curl -fsSL https://raw.githubusercontent.com/kazuterukawamitu/docker-compose-up-d/cursor/bitbank-live-complete-d4a7/scripts/mac_one_paste.sh | bash
```

## LIVE unlock (your Mac / Sakura VPS — not this cloud agent)

1. Put `BITBANK_API_KEY` / `BITBANK_API_SECRET` in `.env` (never commit; rotate if pasted in chat).
2. `bash scripts/enable_live.sh`
3. `PYTHONPATH=src python3 -m bitbank_bot --check-config` → expect `LIVE_ALLOWED=true`
4. `bash start.sh --screen` or `ENABLE_LIVE=1 bash scripts/vps_deploy.sh` on the VPS **after** SSH works.

## Chan-pro analogue

ちゃんプロ (https://chanpro.jp/) is a kids’ Python course with AI one-error fixes — **not** embeddable here. Local equivalents already in-tree: `scripts/bug_scan.py`, `scripts/gap_agent.py`, `scripts/verify_agent_loop.py`.

## Non-claims (binding)

Profit, 100% foresight, “all bugs gone forever”, VPS install-from-here, and LIVE fills without keys are **not** claimed.
