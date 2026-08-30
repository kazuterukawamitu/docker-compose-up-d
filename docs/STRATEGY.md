# BTC/JPY moving-average strategy

Distilled spec. Authority order:

1. [README.md](../README.md) — percent take-profits and “buy possible amount / sell all”
2. This file — state-machine mapping
3. [MASTER-POLICY.md](MASTER-POLICY.md) — one pair, one sizer, one numeric table
4. Wiki footer text in the `ビットコイン*.html` dumps (Granville-style crosses; no percents)

Default runtime is **dry-run**. Live `POST /v1/user/spot/order` stays out of git.

## Market

- Exchange: Bitbank only
- Pair: `btc_jpy`
- Min order size: 0.0001 BTC
- Price tick: 1 JPY
- Buy size: possible amount (JPY `free_amount` / price, quantized)
- Sell size: all free BTC (quantized)
- Primary candle: `1hour` SMA(20); golden cross SMA(20)/SMA(50)
- Timezone: Japan (JST)

## README rules (authoritative percents)

Priority: **SELL > TAKE_PROFIT > BUY**. No sell on the entry candle. WAIT always has a reason.

### Buys (possible amount)

| ID | When | Take profit |
| --- | --- | --- |
| R1 / BUY1 | MA was in a downtrend, then flattened or turned up, **and** BTC crosses **above** the MA | +3% |
| R2 / BUY2 | MA is in an **uptrend** and BTC crosses **below** the MA | +8% if golden cross, else +5% |
| R3 / BUY3 | Price was **≥5% above** the MA, declined **without touching** the MA, then rose again | +4% |
| R4 / BUY4 | Price was **≥5% below** a **downtrending** MA, then rose again | +5% |

### Sells (flatten)

| ID | When |
| --- | --- |
| R5 / SELL1 | Price was **≥4% above** the MA, then declined |
| R6 / SELL2 | Price declines **and** crosses below the MA, then keeps falling |
| R7 / SELL3 | Price crosses **up** through a MA that is still in a **downtrend** |
| R8 / SELL4 | Price was **≥4% below** the MA, rose **without reaching** the MA, then fell again |

Trend uses `slope = (ma - prev_ma) / prev_ma` versus `MA_SLOPE_THRESHOLD=0.0005`.

Crossover price is linearly interpolated; `crossover_price * 0.01` is stored.

## Wiki-only extras (off by default)

`WIKI_CROSS_RULES=false`. When enabled:

- Short MA crossing long MA upward → `WIKI_GOLDEN` buy
- Short MA crossing long MA downward → `WIKI_DEAD` sell

README already uses golden cross only to pick R2’s +8% vs +5%.
