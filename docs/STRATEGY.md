# BTC/JPY moving-average strategy

Authority: [README.md](../README.md) percents and “buy possible amount / sell all”.

## Market

- Exchange: Bitbank only
- Pair: `btc_jpy`
- Min order size: 0.0001 BTC
- Price tick: 1 JPY
- Buy size: possible amount, capped by `FIXED_ORDER_BTC` (default `0.001`, the backtest lot). `FIXED_ORDER_BTC=0` removes the cap.
- Sell size: the tracked position, never the rest of the wallet. Paper mode with no keys sells that position even when the paper BTC ledger is still 0.
- Hard stop: `STOP_LOSS_PCT` (default `0.03`) sells when close is at or below fill average × (1 − stop), including the entry candle. `0` disables it.
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

## Live mark, fees, and the daily screen

Pattern BUY1–4 and SELL1–4 still read the closed candle. A resting position can
also exit from the public ticker: at `average × (1 − STOP_LOSS_PCT)` the bot
sends `STOP_ORDER_TYPE` (default market), and at `average × (1 + tp)` it sends
a limit. That path runs only when the ticker has a timestamp.

Realized PnL subtracts the taker fee (default 0.12% each side, about 0.24%
round trip). A 0.05% scalp on 0.001 BTC does not clear that cost. BUY1 at +3%
does. `DAILY_PNL_FLOOR` and `DAILY_PROFIT_TARGET` block new buys. They do not
replace Granville and they do not flatten an open position. Entropy and the
down posterior do the same, and only after 8 return samples. The 取引画面 shows
日次損益 next to the position.
