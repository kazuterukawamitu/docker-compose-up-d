# BTC/JPY moving-average strategy

Authority: [README.md](../README.md) percents and “buy possible amount / sell all”.

## Market

- Exchange: Bitbank only
- Pair: `btc_jpy`
- Min order size: 0.0001 BTC
- Price tick: 1 JPY
- Buy size: possible amount (`free_amount` JPY × usage × fee buffer / price, quantized)
- Sell size: all free BTC (quantized)
- Primary candle: `1hour` SMA(20); golden cross SMA(20)/SMA(50)
- Timezone: Japan (JST)

## README rules

Priority: **SELL > TAKE_PROFIT > BUY**. No sell on the entry candle. HOLD always has a reason.

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

## Higher-timeframe filter (not a second strategy)

When `ENABLE_HTF_FILTER=true` (default), a **new BUY** is blocked if the 4-hour
and 1-day SMA slopes are both DOWN, or if those candles cannot be read. Sells
and take-profit are unchanged. `--synthetic` smoke tests skip this filter.
