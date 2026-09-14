# Dev environment (Mac iTerm → Sakura VPS)

This repository is the bot. It does **not** install a machine-wide `.zshrc`.

## Local (MacBook Air + iTerm)

```bash
cd "$HOME/docker-compose-up-d"
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp -n .env.example .env
python3 launch.py
```

Do not run `python3 main.py` from `~`. Smoke (exits on purpose):

```bash
python3 launch.py --once --synthetic --skip-lock --no-screen
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
