# Requirements matrix (operator request ↔ code)

Status codes: `done` | `partial` | `blocked` | `n/a` | `verify_on_host`

| ID | Request theme | Target | Evidence now | Gap vs purpose | Action | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R01 | Save original request | `docs/audit_artifacts/` | BITBANK_FULL_REQUEST.md | — | keep verbatim intent | done |
| R02 | Identify Mac vs VPS bot | deploy docs | Mac screen DRY_RUN; VPS SSH not available here | cannot prove VPS hash | `scripts/vps_deploy.sh` | blocked |
| R03 | `bitbank_bot.config/rest_client/main/watchdog` exist | `src/bitbank_bot/` | files present; gap_agent SYNTAX | Mac may run old `run.py` only | `mac_one_paste.sh` | done |
| R04 | SELL delay / intrabar exits | `decision.py` `engine.py` | gap SELL_INTRABAR PASS | — | keep ticker STOP/TP | done |
| R05 | STOP / emergency market | `decision.py` `orders.py` | gap STOP_MARKET PASS | — | market protective sells | done |
| R06 | Cancel clears pending | `orders.py` `engine.py` | gap CANCEL_PENDING PASS | — | — | done |
| R07 | Partial fill incremental notional | `orders.py` `engine.py` | gap PARTIAL_NOTIONAL PASS | — | — | done |
| R08 | Fee-aware PnL | `engine.py` `orders.py` | gap FEE_PNL PASS | — | TAKER_FEE_RATE fallback | done |
| R09 | Startup reconcile incl. sells | `engine.py` | gap RECONCILE + SELL_RECONCILE PASS | needs LIVE keys on host | — | done |
| R10 | BUY scarcity (5%→max%) | `strategy.py` `config.py` | BUY4 FLAT+1% dip; tests | still MA-gated | FLAT allowed | done |
| R11 | Unlock DRY_RUN → LIVE | `enable_live.sh` `config.py` | dual confirm + TRADING_MODE | keys missing in cloud | operator runs enable_live | verify_on_host |
| R12 | V31 + OOS simultaneous | `v31.py` `oos.py` `dual_run.py` | dual_run wired; OOS execute=false | — | shadow never orders | done |
| R13 | shadow/guard timers active | `loop_timers.py` | active only while run_forever | env YES alone ≠ active | evidence-based | done |
| R14 | Private API / LIVE / OOS YES | evidence report | separate flags | LIVE YES needs keys | `--check-config` | partial |
| R15 | Docker verify agents | `docker-compose.yml` profile verify | compose + verify_agent_loop | VPS install not run here | `vps_deploy.sh` | partial |
| R16 | Quantum / KY metaphors | `quantum_engine.py` | classical adaptive layer | not quantum hardware | documented | done |
| R17 | Pareto priority | gap_agent order | high-impact execution gaps first | — | — | done |
| R18 | Daily PnL + Granville coexist | `decision.py` `engine.py` | entropy + daily flatten | — | — | done |
| R19 | Shannon entropy | `decision.py` | wired | — | — | done |
| R20 | Ultra-fast paste | `paste.sh` `mac_one_paste.sh` | scripts | — | — | done |
| R21 | Archive zip以外 | `make_archive.sh` | tar.gz default | — | — | done |
| R22 | Real Bitbank LIVE fill | private API | not executed (no keys / no VPS) | credentials + host | operator | blocked |
| R23 | Profit / 完成成功 claim | n/a | refused without fills | — | do not claim | n/a |
| R24 | Chan-pro scanner | `bug_scan.py` | present | — | — | done |
| R25 | Origin CLI auth | Mac user | user logged in locally | cloud agent refuses stored login | n/a here | done |
| R26 | HTF filter | `multi_timeframe.py` | blocks BUY when both HTF DOWN | can be disabled | ENABLE_HTF_FILTER | done |
| R27 | Realtime size bounds | `amounts.py` | free_amount * MAX_BALANCE_USAGE | — | — | done |
| R28 | webpack parallel | n/a | no webpack app in bot | — | skip | n/a |
| R29 | Halting problem / 100% foresight | n/a | refused | — | — | n/a |
| R30 | Self-healing / circuit breaker | `risk.py` `quantum_engine` | present | — | — | done |

## Verification commands

```bash
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 scripts/gap_agent.py
PYTHONPATH=src python3 scripts/bug_scan.py
PYTHONPATH=src python3 -m bitbank_bot --check-config
PYTHONPATH=src python3 -m bitbank_bot --once --synthetic --no-screen
bash scripts/make_archive.sh
```
