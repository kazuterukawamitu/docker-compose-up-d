# Optional iTerm / zsh helpers for this repo.
#   source /path/to/docker-compose-up-d/scripts/iterm_dev_env.zsh
# Does not replace your ~/.zshrc. Safe to re-source.

typeset -U path
path=(/opt/homebrew/bin /usr/local/bin /usr/bin /bin $path)

export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8
export PYTHONDONTWRITEBYTECODE=1

REPO="${BITBANK_BOT_ROOT:-$HOME/docker-compose-up-d}"
if [[ -d "$REPO/.venv" ]]; then
  # shellcheck disable=SC1091
  source "$REPO/.venv/bin/activate"
  export VIRTUAL_ENV_DISABLE_PROMPT=1
fi
if [[ -d "$REPO/src" ]]; then
  export PYTHONPATH="$REPO/src${PYTHONPATH:+:$PYTHONPATH}"
fi

setopt NO_BEEP
setopt INTERACTIVE_COMMENTS

# Large log tails should not freeze the session; use less -R if needed.
alias bot-log='tail -n 200 -F "$REPO/logs/bot.log"'
alias bot-dry='cd "$REPO" && ./start.sh --screen'
alias bot-ready='cd "$REPO" && echo "Set TRADING_MODE=live_ready in .env first"'
