# How to send large Bitbank-bot specs

Cursor New Chat cannot hold five huge pasted documents. Three still often fail.
Do **not** paste the bot into chat. The project is already in this git repo.

## What to do instead

1. Keep working in this repository (`src/bitbank_bot/`).
2. Put extra specs in `docs/` (this file, `AUDIT.md`, `STRATEGY.md`).
3. Point Cursor at the checkout. The agent reads files; it does not need a
   100k-line paste.
4. For follow-ups, send `END OF PROMPT` plus the delta you want. Do not
   resend the entire specification unless something changed.

## What this bot actually is

- Pair: Bitbank `btc_jpy` only.
- Live program: `python3 main.py` or `./start.sh` (needs httpx).
- `run.py` is a DRY_RUN 取引画面. It never calls `create_order`.
- Default: `DRY_RUN=true`. LIVE needs keys plus
  `LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK`.

iTerm Shell Integration cannot be installed from this Cloud VM. Use
`scripts/iterm_dev_env.zsh` on the Mac (`source`, do not overwrite `~/.zshrc`).
