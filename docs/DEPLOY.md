# Deploy / LIVE enable (Mac + Sakura VPS)

This agent VM could not SSH to `rocky@49.212.212.148` (`Host key verification failed`).
Definitions and scripts below are ready; you run them on Mac or the VPS.

Secrets stay in `.env` only. Never paste API keys into chat.

## Ultra-fast paste — DRY_RUN 取引画面 (Mac)

```bash
cd ~/docker-compose-up-d 2>/dev/null || git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git ~/docker-compose-up-d
cd ~/docker-compose-up-d && git fetch origin && git checkout -B cursor/bitbank-full-audit-fix-98dc origin/cursor/bitbank-full-audit-fix-98dc
bash paste.sh
```

Or stdlib-only (no pip):

```bash
python3 run.py
```

`HOLD` / `no_buy_setup` / `LONG_WAIT` with `DRY_RUN` means the bot is alive and waiting for a Granville setup. Cycles count polls (~15s), not closed 1h bars.

## Ultra-fast paste — enable LIVE (requires keys already in `.env`)

```bash
cd ~/docker-compose-up-d   # or /home/rocky/bitbank-bot on VPS
cp -n .env.example .env
# edit .env: set BITBANK_API_KEY and BITBANK_API_SECRET
bash scripts/enable_live.sh
PYTHONPATH=src python3 -m bitbank_bot --check-config
# Expect MODE=LIVE LIVE_ALLOWED=true only when keys + dual flags are set
bash start.sh --screen
```

`enable_live.sh` refuses if keys are empty. It does **not** place an order by itself.

## Docker on VPS

```bash
cd /home/rocky/bitbank-bot   # adjust if your path differs
cp -n .env.example .env
# set keys; then:
bash scripts/enable_live.sh
docker compose up -d --build
docker compose logs -f bitbank-bot

# verification / gap agents (no orders)
docker compose --profile verify up -d --build verify-agent gap-agent
docker compose -f docker/compose.audit.yml up --build
```

systemd alternative: `deploy/bitbank-bot.service` (WorkingDirectory + EnvironmentFile=.env).

## What this does **not** prove from the Cloud Agent alone

| Success type | This session |
| --- | --- |
| Connection (VPS) | BLOCKED (SSH host key) |
| Connection (Bitbank public) | Available via public API tests |
| Connection (Bitbank private) | Needs your keys on the host |
| Runtime DRY_RUN | Verified locally |
| LIVE order / fill / profit | NOT verified here — run on VPS after enable_live |

## Rollback

```bash
# stop containers / service
docker compose down
# or: sudo systemctl stop bitbank-bot

# restore paper mode
sed -i 's/^DRY_RUN=.*/DRY_RUN=true/' .env
sed -i 's/^LIVE_TRADING=.*/LIVE_TRADING=false/' .env
sed -i 's/^TRADING_MODE=.*/TRADING_MODE=DRY_RUN/' .env
# restore previous git tag/commit if needed
```
