# Dev environment (Mac iTerm → Sakura VPS)

This repository is the bot. It does **not** install a machine-wide `.zshrc`.

## Local (MacBook Air + iTerm)

```bash
cd /path/to/docker-compose-up-d
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp -n .env.example .env
python3 run.py
# or full package:
PYTHONPATH=src python3 -m bitbank_bot --dry-run --skip-lock --max-cycles 1 --synthetic --no-screen
```

Optional zsh snippet (append yourself):

```zsh
# bitbank bot
export PATH="$HOME/.local/bin:$PATH"
if [ -d "$HOME/docker-compose-up-d/.venv" ]; then
  alias bitbank-venv='source "$HOME/docker-compose-up-d/.venv/bin/activate"'
fi
```

iTerm2/5 Shell Integration: install from iTerm’s menu. It does not change trading logic.

## VPS

Run the bot under systemd (`deploy/bitbank-bot.service`). Keep `DRY_RUN=true` until LIVE_READY looks correct in `logs/bot.log`.

LIVE on VPS:

```
TRADING_MODE=live
DRY_RUN=false
LIVE_TRADING=true
LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK
```

plus Bitbank API key/secret and IP whitelist. Never commit `.env`.
