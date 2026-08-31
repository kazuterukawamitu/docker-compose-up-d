# Concatenated prompt vs this repository

A large paste of prior Cursor chats asked to “complete the iterm15 program suite after fixing three or four bugs.” `iTerm15` is the Mac iTerm **window** that SSHes to Sakura VPS. It is not a second product.

This branch is the single Bitbank suite. Earlier overlapping bots ([PR #2](https://github.com/kazuterukawamitu/docker-compose-up-d/pull/2), [#4](https://github.com/kazuterukawamitu/docker-compose-up-d/pull/4), [#5](https://github.com/kazuterukawamitu/docker-compose-up-d/pull/5), [#6](https://github.com/kazuterukawamitu/docker-compose-up-d/pull/6)) stay historical.

## Four bugs fixed here

1. Bot dies when Mac / iTerm15 / SSH / J:COM drops — systemd `Restart=always` plus `scripts/install-vps.sh`. Do not run `python bot.py` inside SSH.
2. Logs look like trades while Bitbank JPY never moves — dry-run logs `[ORDER_INTENT]` / `[SIMULATED_FILL]` only; `[FILL]` requires `executed_amount > 0`.
3. Launch from `~` (`requirements.txt` missing, `No module named bitbank_bot`, `pip` not found) — `bash ./start.sh` cds to the clone, requires Python 3.12, uses venv `python -m pip`.
4. Scattered numbers — one Master Policy in `src/bitbank_bot/config.py`, `.env.example`, and [MASTER-POLICY.md](MASTER-POLICY.md).

## Keep

- Bitbank `btc_jpy` only
- README R1–R8 percents
- Dry-run default
- Min 0.0001 BTC, tick 1 JPY
- VPS-resident systemd (Mac is monitor-only)

## Discard

- Coincheck / GMO Coin / bitFlyer clients
- LSTM / LightGBM / XGBoost / quantum
- Discord / LINE
- Compress-to-500-lines
- Pasting Python into zsh
- Committing API keys or VPS passwords
- This agent SSHing to the user’s Sakura box (the install script is the deliverable)

HTML wiki dumps in the repo root are identical footer pages, not charts. Leave them as-is.
