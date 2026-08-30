# Master Policy

One Bitbank BTC/JPY bot. One pair. One sizer. One numeric table.
`iTerm15` is the Mac window that SSHes to the VPS; it is not a second program.

Canonical constants live in [`src/bitbank_bot/config.py`](../src/bitbank_bot/config.py).
Dataclass defaults, `load_config`, [`.env.example`](../.env.example), and this file must match.

## Identity

- Exchange: Bitbank only
- Display pair: BTC/JPY
- API pair: `btc_jpy`
- Rejected aliases: `btc_jpn`, `JPN/BTC`, `JPC/BTC`, `jpy_btc`
- Public REST: `https://public.bitbank.cc`
- Private REST: `https://api.bitbank.cc/v1`
- WebSocket: `wss://stream.bitbank.cc/socket.io/?EIO=4&transport=websocket`
- Mac / iTerm15: monitor and SSH only
- Process owner: systemd on the VPS (`Restart=always`)

## Timeframes

Primary R1–R8 series: `CANDLE_TYPE=1hour`.

Health map (logged, not score-summed):

- `1m` → `1min`
- `5m` → `5min`
- `15m` → `15min`
- `30m` → `30min`
- `1h` → `1hour`
- `4h` → `4hour`
- `1d` → `1day`
- `1w` → `1week`

`MTF_FILTER` defaults off. The forming candle is dropped, not traded.

## Moving average

- Kind: `sma`
- Period: 20
- Short / long (golden cross): 20 / 50
- Slope threshold: `0.0005` (`UP` / `FLAT` / `DOWN`)

## README take-profits and extensions

- BUY1 take-profit: +3%
- BUY2 take-profit: +8% on golden cross, else +5%
- BUY3 take-profit: +4% after +5% extension pullback
- BUY4 take-profit: +5% after −5% dip
- SELL1: decline after +4% above MA
- SELL4: failed recovery after −4% below MA

Wiki-only golden/dead-cross extra rules stay behind `WIKI_CROSS_RULES=false`.

## Sizing (PositionSizer only)

Strategy must not set quantity. [`src/bitbank_bot/amounts.py`](../src/bitbank_bot/amounts.py) `PositionSizer` recalculates from `free_amount` every order.

- Buy: possible amount (`MAX_BALANCE_USAGE=0.95` minus fee buffer)
- Sell: all free BTC × `0.999`
- Min size: `0.0001` BTC
- Amount step: `0.0001` BTC
- Price tick: 1 JPY
- Honor exchange `min_amount` / `limit_max_amount`

## Risk

- `DAILY_PNL_FLOOR=150` JPY (halt when realized daily PnL ≤ −150)
- Extra `MAX_DAILY_LOSS_JPY` optional (empty = disabled)
- Kill file: `data/KILL`
- Stale data: 60 seconds
- Watchdog: 900 seconds (`NORMAL_WAIT` / `LONG_WAIT` / `FAIL`)
- Single-instance lock: `data/bot.lock`

## Execution honesty

- Default `DRY_RUN=true`. Live needs `DRY_RUN=false` **and** `LIVE_TRADING=true` plus keys in local `.env`.
- Dry-run never calls `POST /v1/user/spot/order`.
- Dry-run paper fills log `[SIMULATED_FILL]` and `bitbank_jpy_unchanged=true`, never `[FILL]` or “TRADE SUCCESS”.
- A real `[FILL]` requires `executed_amount > 0` from Bitbank.
- Read-only audit: `python -m bitbank_bot --audit` or `scripts/bitbank_execution_audit.py`.

## Pipeline

`multi_timeframe` (health) → `strategy` (R1–R8) → `risk` → `PositionSizer` → `orders` → Bitbank
