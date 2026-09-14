# Output program inventory (disclosed)

Definition: runnable entrypoints that write user-visible output
(取引画面, launcher text, diagnostics, audit, tests wrapper).
Library modules and pytest files are not counted.

## vs origin/main

| Snapshot | Count | Change |
| --- | --- | --- |
| origin/main | 6 | baseline |
| this branch `cursor/closed-loop-launcher-563e` | 11 | **+5** |

Removed: **none**.

## Programs on origin/main (kept)

1. `start.sh` — opens 取引画面 (now via `bitbank_bot.launch`)
2. `run.py` — stdlib 取引画面, never orders
3. `main.py` — package or `run.py` fallback
4. `python -m bitbank_bot` (`src/bitbank_bot/main.py`)
5. `diagnostics.py` — JSON env check, no secrets
6. `scripts/bitbank_execution_audit.py` — read-only private/public audit

## Added on this branch (+5)

7. `src/bitbank_bot/launch.py` — enhanced program-launching program
8. `scripts/home_start.sh` — home-directory finder (does not start the bot)
9. `scripts/install_launch_alias.sh` — installs that finder
10. `scripts/run_bot.sh` — cwd guard, then `start.sh`
11. `scripts/run_tests.sh` — pytest only, not 取引画面

## Library modules added (not output programs)

- `execution_gate.py`
- `rate_engine.py`
- `reconciliation.py`
- `trade_signal_executor.py`
- `pytest_plugin.py` (pytest cwd guard)

The launcher prints this inventory at start (`PROGRAM_INVENTORY vs origin/main`).
