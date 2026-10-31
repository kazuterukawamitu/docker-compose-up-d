# Bitbank BTC/JPY — formal request (saved verbatim intent)

This file records the operator request as the binding specification for this
branch. Repeated motivational / metaphor language is kept as *intent*, not as
proof of completion. Concrete engineering work maps metaphors to classical
modules (`quantum_engine.py`, `decision.py`, `dual_run.py`).

## Operator evidence (2026-10-31 JST)

Observed Mac iTerm screen while DRY_RUN:

- `btc_jpy` DRY_RUN / 実注文なし / cycles≈14000+ / up≈80ks
- Signal: `HOLD` / `no_buy_setup` / trend `FLAT` / 建玉なし / `LONG_WAIT`
- Footer: 「HOLD/待機は正常です。このプログラムは注文しません」
- `.env` reported: `TRADING_MODE=DRY_RUN`, `DRY_RUN=true`, `LIVE_TRADING=false`
- Mode dump: `MODE=DRY_RUN`, `LIVE_ALLOWED=False`, `BLOCK_REASON=dry_run`
- Origin CLI on Mac: `origin auth login` succeeded as `kazuteru1974@icloud.com`

## Formal success criteria (must not be conflated)

| Criterion | Meaning | Evidence required |
| --- | --- | --- |
| 接続成功 | VPS + Bitbank public/private API auth | HTTP/WS success; private assets/orders when LIVE |
| 稼働成功 | Correct source+config continuous loop | systemd/docker up; matching source hash |
| 判断成功 | BUY/SELL/HOLD rules evaluate correctly | strategy tests + live logs |
| 実行成功 | Intended order accepted by Bitbank | private order id |
| 約定成功 | Fill qty/price matches trade history | trade_history reconcile |
| 実績成功 | Fee-aware realized PnL | fee fields or TAKER_FEE_RATE estimate logged |
| 完成判定 | Requirements matrix closed with leftovers listed | this folder |

## Declared non-claims

- Profit / “未来予知 100%” / “全バグ不存在” / “停止問題の一般解決” are **not** claimed.
- Quantum wording = classical adaptive search (`quantum_engine.py`), not quantum hardware.
- LIVE is **not** enabled in CI/cloud without operator keys on the target host.
- This cloud agent cannot SSH to `rocky@49.212.212.148` without credentials.

## Priority defects from operator table

1. SELL delay on closed 1h bars → ticker STOP/TP (`decision.price_exit`)
2. Missing STOP market path → STOP + market replace
3. Cancel leaves pending → clear on canceled
4. Partial fill cost uses cum-avg × delta → `incremental_notional`
5. Fee-blind realized PnL → fee_jpy / TAKER_FEE_RATE
6. No exchange reconcile on boot → `Engine.reconcile` (incl. open sells)

## BUY scarcity root cause (confirmed)

Operator screen showed **FLAT** + `no_buy_setup`. BUY4 previously required
`Trend.DOWN` only, so FLAT hours never entered the dip machine. Defaults also
used a 5% dip. This branch: BUY4 allows DOWN/**FLAT**, default dip/extend **1%**,
size still `free_amount * MAX_BALANCE_USAGE` (realtime upper bound).

## LIVE unlock procedure (operator host)

```bash
# 1) put keys in .env (never commit)
# 2) flip gates
bash scripts/enable_live.sh
# 3) verify (no order)
PYTHONPATH=src python3 -m bitbank_bot --check-config
# 4) run
bash start.sh --screen
# or Docker
docker compose up -d --build
```

## Chan-pro style scanners

「ちゃんプロ」(chanpro.jp) uses AI one-error-at-a-time fixes. Local analogues:

- `scripts/bug_scan.py` — one finding per anti-pattern
- `scripts/gap_agent.py` — purpose vs package PASS/FAIL
- `docker compose --profile verify up` — continuous verify-agent
