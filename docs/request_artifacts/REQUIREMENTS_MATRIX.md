# REQUIREMENTS_MATRIX.md
# Generated 2026-11-04 (Asia/Tokyo). "完了/達成" in the original request are TARGETS, not evidence.

| ID | Source theme | Target | Current evidence | Gap | Action this branch | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R01 | Full source audit | Inventory bot package | src/bitbank_bot/* present; import ok | — | Documented in docs/AUDIT.md | DONE |
| R02 | Missing bitbank_bot.config etc. | Modules importable | config/rest_client/main/watchdog under src/bitbank_bot | Needs PYTHONPATH=src | start.sh / README | DONE |
| R03 | SELL delay (1h candle) | Intra-bar STOP/TP | price_exit + protective market sell | — | Already on main; gap_agent PASS | DONE |
| R04 | STOP/emergency market | Independent STOP path | decision.price_exit STOP + market | Soft poll, not exchange stop order | Documented limit | DONE (soft) |
| R05 | Cancel leaves pending | Clear pending | classify_order + _poll_pending | — | gap_agent PASS | DONE |
| R06 | Partial fill avg bug | Incremental notional | incremental_notional() | — | gap_agent PASS | DONE |
| R07 | Fees ignored | Fee-aware PnL | fee_jpy deducted; reconcile sell fee estimated | — | Fixed reconcile omission | DONE |
| R08 | Startup reconcile | Assets + active orders | Engine.reconcile (live only) | Dry-run skips (by design) | gap_agent PASS | DONE |
| R09 | DRY_RUN blocks orders | Dual LIVE confirm | may_place_live_orders | User .env still DRY_RUN | enable_live.sh (needs keys) | PARTIAL |
| R10 | BUY scarcity / no_buy_setup | More Granville setups | BUY3/BUY4 extend/dip 0.05→0.01; HTF fail-open | Market may still HOLD | Config + HTF change | DONE |
| R11 | Granville + daily PnL + entropy | Coexist | decision.py wired | — | Verified | DONE |
| R12 | V31 + OOS simultaneous | Shadow no orders | dual_run + v31.py + oos.py | Timers active only while loop runs | Wired | DONE |
| R13 | Docker audit agent | Purpose gap agent | docker/compose.audit.yml + verify profile | VPS SSH not reachable from this VM | Definitions ready | PARTIAL |
| R14 | Sakura VPS deploy | Install + systemd/docker | deploy/bitbank-bot.service | SSH host key failed to 49.212.212.148 | Manual steps in docs/DEPLOY.md | BLOCKED_HERE |
| R15 | Bitbank LIVE fill + profit | Real orders + fee PnL | Code path ready | No keys on this agent; no LIVE proof | Operator enable_live.sh | NOT_VERIFIED |
| R16 | Chan-pro bug finder | One finding per hit | scripts/bug_scan.py (analogue; chanpro.jp is kids course AI editor, not installable API) | Not identical product | Documented + used | DONE |
| R17 | Quantum / wavefunction claims | Classical adaptive layer | quantum_engine.py | Not quantum hardware | Explicitly classical | DONE |
| R18 | Perfect prediction / halt problem | Do not claim | — | Impossible | Refused false claims | N/A |
| R19 | Paste ultra-fast | One-block scripts | paste.sh, enable_live.sh, DEPLOY.md | — | Added | DONE |
| R20 | Delivery non-zip | tar.gz | scripts/make_archive.sh | — | Prefer tar.gz | DONE |
| R21 | User paste HOLD cycles | Explain idle | no_buy_setup + DRY_RUN + LONG_WAIT | Not a crash | Screen note clarified | DONE |
| R22 | MAX buy % | Use max usable balance | MAX_BALANCE_USAGE=0.95 already | Not 5% size | Documented (5% was BUY3_EXTEND) | DONE |
| R23 | Shadow/guard YES | Active with loop | loop_timers evidence-based | YES only when run_forever cycles | Not faked at check-config | DONE |
| R24 | Catch-up drops pattern SELL | Defer missed-bar sell to current bar | Was observe-only + advance ts | Lost exit on downtime catch-up | deferred_sell in engine.py | DONE |
| R25 | Patches 0002 / 0005 | Locate external patch files | Not in this git history | Names are V53-sandbox external | Do not claim applied; use in-tree five patches | N/A |
| R26 | VPS identity 2026-11-05 | Canonical vs running | systemd dead; dry-run transfer PID | Not LIVE | VPS_STATE_20261105.md + ONE_LINERS | PARTIAL |
| R27 | V31/OOS order authority | OOS never orders | dual_run shadow_has_order_authority=False | — | Confirmed in audit | DONE |
| R28 | pending notional missing | Restore from venue/history or block | Was PARTIAL (avg_price only) | Double-book risk on next slice | `_repair_pending_basis` + trade_fill_basis | DONE |
| R29 | Zero execution JPY fill | Reject ledger write | Accepted `actual_jpy==0` | Phantom zero-cost size | `_apply_fill` rejects <=0 | DONE |
