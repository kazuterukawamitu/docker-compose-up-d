# BTC/JPY moving-average strategy

This is the distilled trading spec for this repository. Sources, in order of authority:

1. [README.md](../README.md) — percent take-profits and “buy possible amount / sell all”
2. GitHub Wiki footer text saved in the `ビットコイン*.html` dumps (Granville-style crosses; no percents)
3. Bitbank market constraints (not in the README, required to size orders)

There is no Python bot on `main`. Implementations live in existing PRs:

- [PR #1](https://github.com/kazuterukawamitu/docker-compose-up-d/pull/1) — offline backtester (`mlbot/`)
- [PR #2](https://github.com/kazuterukawamitu/docker-compose-up-d/pull/2) — Bitbank dry-run bot (`src/bitbank_bot/`, `GranvilleStrategy` rules 1–8)

Default runtime is **dry-run**. Live `POST /v1/user/spot/order` is out of scope unless someone later sets that explicitly **locally** (never in git).

## Market

| Item | Value |
| --- | --- |
| Exchange | Bitbank only |
| Pair | `btc_jpy` |
| Min order size | 0.0001 BTC |
| Price tick | 1 JPY |
| Buy size | Possible amount (JPY balance / price, quantized to 0.0001 BTC) |
| Sell size | All BTC held (quantized; dust below 0.0001 BTC cannot be sent) |

Moving-average period is **not specified** in the README. Treat SMA period as a parameter (PR #2 uses a configurable SMA plus fast/slow MAs for golden-cross detection).

Timezone in the README Docker fragment is `Japan` (JST).

## README rules (authoritative percents)

Buy = “possible amount”. Sell = “all BTC”. Take-profit percents are from the fill price.

### Buys

| ID | When | Take profit |
| --- | --- | --- |
| R1 | MA was in a downtrend, then flattened or turned up, **and** BTC price crosses **above** the MA | +3% |
| R2 | MA is in an **uptrend** and BTC price crosses **below** the MA (dip buy) | +8% if a golden cross is active, else +5% |
| R3 | Price was **≥5% above** the MA, then declined **without touching** the MA, then rose again | +4% |
| R4 | Price was **≥5% below** a **downtrending** MA, then rose again | +5% |

### Sells (flatten)

| ID | When |
| --- | --- |
| R5 | Price was **≥4% above** the MA, then declined |
| R6 | Price declines **and** crosses below the MA (except when R2 applies: uptrend dip-buy) |
| R7 | Price crosses **up** through a MA that is still in a **downtrend** |
| R8 | Price was **≥4% below** the MA, rose **without reaching** the MA, then fell again |

PR #2 encodes these as `GranvilleStrategy` rules 1–8. Conflict handling there: sells are evaluated before buys; R2 (uptrend cross-down) overrides R6.

## Wiki footer rules (same ideas, no percents)

Thirteen of the fourteen HTML files are identical copies of the wiki `_フッター` editor page. That page restates the pattern without 3/4/5/8% numbers, and adds explicit dual-MA crosses:

| Wiki line | Maps to | Notes |
| --- | --- | --- |
| Downtrend MA flattens or rises, price crosses above MA → buy | R1 | No TP in wiki; README says +3% |
| Uptrend MA, price crosses below MA → buy | R2 | No TP; README says +8% / +5% |
| Large plus divergence, pullback without touching MA, then rise → buy | R3 | Wiki “large”; README ≥5%, TP +4% |
| Large minus divergence under downtrend MA, then rise → buy | R4 | Wiki “large”; README ≥5%, TP +5% |
| Short MA turning **up** crosses long MA from below → buy | Golden cross | **Wiki-only buy.** README uses golden cross only to pick R2’s +8% vs +5% |
| Large plus divergence → sell | Related to R5 | Wiki sells on extension itself; README waits for a decline after ≥4% |
| Price starts falling and crosses below MA → sell | R6 | |
| Price crosses up through a downtrending MA → sell | R7 | |
| Large minus divergence, bounce fails to reach MA, then falls → sell | R8 | Wiki “large”; README ≥4% |
| Short MA turning **down** crosses long MA downward → sell | Dead cross | **Wiki-only sell.** Not a separate README rule |

If a later patch on PR #2 is wanted, the wiki-only golden/dead-cross lines are the gap — not a new bot.

## Intentionally unspecified

The original notes do not define:

- SMA / EMA length, or what “flat” vs “up” vs “down” MA trend means numerically
- Whether “possible amount” is 100% of JPY or a fraction
- Stop-loss (PR #2 adds one in the risk manager; that is extra, not README)
- Candle timeframe (HTML filenames say 3m / 5m / 10m / … / 1w but the files are the same wiki footer, not charts)

Do not invent live-trading behavior to fill those gaps. Keep them as parameters or leave them unimplemented.
