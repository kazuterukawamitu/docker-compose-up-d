# Concatenated prompt vs this repository

A large paste of prior Cursor chats was sent in parts, then “analyze the entire set.” This note is that analysis. It is **not** a license to implement every sentence in the dump.

## Verdict

The paste is **not one spec**. It is contradictory session history (Bitbank, Coincheck, GMO Coin, bitFlyer, VPS, iTerm2, ML, “100% fill”, live loops). Later lines override earlier ones.

This GitHub repo (`kazuterukawamitu/docker-compose-up-d`) on `main` is **not a trading bot**. It is:

- [README.md](../README.md) — Docker locale fragment + Japanese MA rules
- Fourteen saved GitHub Wiki/editor HTML pages named like Bitcoin timeframes
- A default “Hello, world!” Actions workflow

**Do not start a third bot.** Two PRs already exist (see below). Live Bitbank orders, VPS SSH, and secrets must stay out of git.

The canonical strategy table is [STRATEGY.md](STRATEGY.md).

## What to treat as real

Keep only what is **consistent** and **present in this repo** (or required to size a Bitbank order):

| Topic | Decision |
| --- | --- |
| Exchange | Bitbank only (`btc_jpy`) |
| Strategy | README percent rules + wiki footer Granville-style rules |
| Runtime | Python, **dry-run by default** |
| Sizing | Min **0.0001 BTC**, tick **1 JPY** |
| “Balances never move” | Unfilled or **simulated** orders, not a missing UI |

## What to discard

Do **not** implement from the dump:

- Ports to Coincheck, GMO Coin, or bitFlyer
- FOK / IOC “guaranteed fill”, force-orders, or 100% fill-rate
- Live infinite trading loops or enabling live orders in CI/git
- Quantum / qubit language
- Pasting a whole program into iTerm2/zsh (`zsh: event not found` / parse errors)
- This agent SSHing to a Sakura VPS or writing the user’s `~/.ssh/config`
- Prometheus / Grafana / full observability stacks
- LSTM / XGBoost as a production requirement (optional stubs elsewhere are enough)
- Committing API keys, secrets, or VPS host/user/port identity

## Security

The dump included **live-looking** Bitbank API credentials and VPS login details.

- Those values are **not** copied into this repo, this PR, logs, or docs.
- Rotate the Bitbank API key/secret on Bitbank’s site; treat anything pasted into chat as burned.
- If a bot is run locally, use a gitignored `.env`. The repo may only contain `.env.example` **placeholders** (already the approach on [PR #2](https://github.com/kazuterukawamitu/docker-compose-up-d/pull/2)).
- Never log request-signing secrets.

## What the HTML files are

| Files | Content |
| --- | --- |
| 13 × `ビットコイン*.html` | **Byte-identical** browser saves of wiki page `_フッター` (locale snippet + strategy text). Not charts. Not TradingView. |
| 1 × `ビットコイン１日線 · … mlbot-tutorial Wikiのコピー.html` | GitHub “Upload files” page dump; empty editor body |

Timeframe names in the filenames are **labels only**. They do not contain OHLCV.

Leave these files on `main` unless someone explicitly asks to delete the duplicates.

## Existing work (do not duplicate)

| PR | What it is | What it is not |
| --- | --- | --- |
| [#1](https://github.com/kazuterukawamitu/docker-compose-up-d/pull/1) | Python env + offline MA backtester (`mlbot/`, synthetic/CSV) | Not Bitbank, not live |
| [#2](https://github.com/kazuterukawamitu/docker-compose-up-d/pull/2) draft | Bitbank REST (+ optional WebSocket), `GranvilleStrategy` rules 1–8, amount quantization, risk manager, pytest, Docker/systemd **templates**, `.env.example`, `DRY_RUN` default | Not a second architecture; not an invitation to copy the tree onto another branch |

Any code follow-up belongs **on PR #2** (review comment or small patch), for example:

- Wiki-only golden-cross buy / dead-cross sell as extra explicit rules ([STRATEGY.md](STRATEGY.md))
- A test that dry-run never calls `POST /v1/user/spot/order`

This documentation branch does **not** copy `src/bitbank_bot/` or `mlbot/`.

## Out of scope for this change

- Connecting to Bitbank or placing orders
- Changing CI to trade
- Editing or deleting the HTML dumps
- systemd/SSH on a VPS
