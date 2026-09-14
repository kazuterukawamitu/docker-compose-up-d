# Master requirements (this branch)

This file is the single specification used after consolidating the large
multi-part prompt. Duplicate, contradictory, and unexecutable items were
resolved here. The original chat text is not the runtime spec.

## Objective

Bitbank **spot** `btc_jpy` only. “Complete” means the closed loop works when
the strategy and safety gates actually fire — not that the bot is profitable.

Market data → README MA strategy (BUY1–4 / SELL1–4 / HOLD) → risk → size →
order gate → Bitbank private order API (live only) → `order_id` → status /
partial / full fill → paper or exchange ledger → next bar.

## Contradictions resolved

| Conflict | Decision |
| --- | --- |
| “Do not enable live” vs “place real orders aggressively when conditions match” | **Default remains DRY_RUN.** When `DRY_RUN=false` and `LIVE_TRADING=true` and keys are present **and** a BUY/SELL setup is real (not synthetic), `create_order` **must** be called. Tests and `python3 launch.py` without `--live` never place orders. |
| “Rewrite into DataManager / ConnectionManager / …” vs “do not rewrite the architecture” | Keep `Engine` as the loop. Add thin helpers (`execution_gate`, `rate_engine`) instead of a new framework. |
| “Add Fibonacci / extra maxims” vs “pause for approval / do not stack AND filters” | **Not implemented.** Extra strategies would increase perpetual HOLD. BUY_GATE logs explain HOLD. |
| SIGNAL_ONLY | **Does not exist** in this repo. Do not add it. |
| iTerm5 / `.zshrc` / Mac system config | Out of scope for this repository. The launcher is `launch.py` + `start.sh`. |
| “Reply only Please continue” vs `END OF PROMPT` | `END OF PROMPT` wins: implement. |

## Modes

| Mode | How to enable | Bitbank `POST /user/spot/order` |
| --- | --- | --- |
| `dry_run` | default, `DRY_RUN=true` | never |
| `live_ready` | `LIVE_READY=true` or `launch.py --live-ready` | never; logs `WOULD_SUBMIT_ORDER` |
| `live` | `DRY_RUN=false` **and** `LIVE_TRADING=true` **and** API keys, or `launch.py --live` with keys | yes, after gates pass |

Optional extra confirm: if `LIVE_TRADING_CONFIRM` is **set**, it must equal
`YES_I_ACCEPT_REAL_MONEY_RISK` or the bot degrades to `live_ready`.

## Strategy (FIXED rates — do not collapse)

| Signal | Meaning | TP |
| --- | --- | --- |
| BUY1 | MA left downtrend + cross up | +3% |
| BUY2 | Uptrend + cross down | +5% or +8% golden |
| BUY3 | ≥5% above MA, pullback, bounce | +4% |
| BUY4 | ≥5% below downtrend MA, bounce | +5% |
| SELL1–4 / TP | README sells / take profit | flatten |

`RATE_MODE=fixed` (default) uses those TPs. `dynamic` / `auto` only clamp TP
and size from ATR; they do not invent a second strategy and they do not call
Bitbank from strategy code.

## Hard rules

- Pair internally and on the wire: `btc_jpy`.
- No bitFlyer / Coincheck / GMO execution paths.
- Never log API secrets.
- Synthetic / empty public candles: loop continues, **no live orders**.
- Order POST is not retried like GET (duplicate-order risk).
- HOLD always has a reason (`no_buy_setup`, `htf_downtrend`, …).
- 15 minutes of healthy HOLD is `LONG_WAIT`, not a crash.
- Live needs dual flags (or `launch.py --live` which sets both **only** when keys exist).

## Launcher

`python3 launch.py` is the program that starts the bot. `start.sh` execs it
after venv/deps. If httpx is missing, DRY_RUN falls back to stdlib `run.py`
(no orders). Live without httpx exits with a reason (no second live client).
