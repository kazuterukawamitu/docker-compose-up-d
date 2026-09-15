# Closed-loop audit (this branch)

Bitbank `btc_jpy` only. This pass adapted the existing `src/bitbank_bot`
loop. It did not invent a DataManager / ConnectionManager / multi-exchange
stack.

## A. Issues / causes

1. `fetch_candles` swallowed per-day exceptions, logged `candles loaded count=0`,
   then the loop fell back to synthetic bars and blocked orders. A warm
   `CandleCache` could still hold thousands of real closed bars (e.g. 14×288
   5-minute candles ≈ 3900), which looked like “closed candles ready” while
   fetch said 0.
2. `latest_only` fetched only today. Near JST midnight a 5-minute series can
   have zero *closed* bars for the new date.
3. Modes were `DRY_RUN` / `LIVE_TRADING` only. There was no `LIVE_READY`
   would-submit state and no `LIVE_TRADING_CONFIRM` phrase.
4. Heartbeat always printed REST/MARKET OK even after a failed ticker/candle
   fetch.
5. `HOLD` / `no_buy_setup` had a reason string but no BUY_GATE / SELL_GATE
   condition breakdown (users read “no signal” as a dead loop).
6. `RestClient._request` retried POST (including `create_order`) on transport
   / 5xx, which can double-submit.
7. No periodic Bitbank-vs-local reconcile.

## B. Severity

| Item | Severity |
| --- | --- |
| Empty 5m fetch → synthetic ban while cache is real | High (false “no orders” / weak dynamic loop) |
| Midnight date-boundary miss | High for `CANDLE_TYPE=5min` |
| POST retry | High if LIVE is ever enabled |
| Mode dual-auth / LIVE_READY | High (safety + dead-gate) |
| Stale ticker vs candle | Medium |
| Honest heartbeat / BUY_GATE logs | Medium |
| Reconcile | Medium |
| RateMode DYNAMIC halt | Low (FIXED default; strategy TPs unchanged) |

## C. Modified / added / removed files

**Added:** `execution_gate.py`, `trade_signal_executor.py`, `reconciliation.py`,
`rate_engine.py`, tests for modes/gate/candles/reconcile/rate/POST,
`reports/closed_loop_audit.md`.

**Modified:** `config.py`, `rest_client.py`, `market_data.py`, `orders.py`,
`engine.py`, `strategy.py`, `indicators.py`, `preflight.py`, `screen.py`,
`main.py`, `multi_timeframe.py`, `.env.example`, `README.md`, `docs/AUDIT.md`,
`tests/helpers.py`, existing tests.

**Removed:** none.

## D. Modification details

- Candle fetch logs `CANDLE_API_ERROR` (endpoint / http_status / bitbank_code /
  pair / candle_type / date / retry_count). Exceptions are not swallowed as a
  silent empty list when every date fails. Yesterday is always requested for
  short candle types. Cache is used when the latest fetch is empty/error and
  cached bars are real and fresh. Synthetic is never merged into the cache.
- `market_data_real` is true only for Bitbank candles. Accidental synthetic
  → `EXECUTION_BLOCKED` `synthetic_market_data`.
- Modes: `DRY_RUN` / `LIVE_READY` / `LIVE`. LIVE requires
  `TRADING_MODE=LIVE` and `LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK`
  and keys. Then `OrderExecutor` calls `create_order(..., live_confirmed=True)`
  with no extra dead gate. LIVE_READY logs `WOULD_SUBMIT_ORDER` only.
- `ExecutionGate` + `TradeSignalExecutor` sit in front of the existing
  `OrderExecutor`. Strategies still do not call Bitbank order APIs.
- BUY_GATE / SELL_GATE logs trend, crossover, volume, and per-rule flags.
  Strategy thresholds were not relaxed.
- POST `/user/spot/order` is not retried. After a submit exception the executor
  inspects `active_orders` and never POSTs again.
- Periodic `reconcile()` treats Bitbank balances / open orders as source of
  truth and logs `RECONCILE_MISMATCH`.
- `RateEngine` default FIXED keeps BUY1 3% / BUY2 5% or 8% / BUY3 4% / BUY4 5%.
  DYNAMIC halts on stale data or ATR NaN/0. AUTO falls back to FIXED.

## E. What reduced dynamic integration

The public candle path failed closed (empty or exception) → synthetic fallback
→ execute=false, while the screen/strategy still evaluated a cached or
synthetic series. HOLD/`no_buy_setup` and HTF blocks are also normal no-trade
outcomes; they were easy to confuse with a broken order loop.

## F. Test results

`python3 -m compileall` PASS. `PYTHONPATH=src pytest` **165 passed**.
Public Bitbank `btc_jpy` ticker + `5min` YYYYMMDD (today and yesterday, JST)
succeeded from this VM. No private order POST. Cloud tests stay dry-run /
mocked / public API only.

## G. Remaining risks

- LIVE still needs real keys and the confirm phrase on the VPS `.env`.
- HTF 4h+1d filter still blocks BUY when those slopes are down or HTF fetch
  fails (`ENABLE_HTF_FILTER=false` to disable).
- Limit orders can stay `UNFILLED`; JPY/BTC only move after a fill poll.
- `run.py` stdlib launcher remains DRY_RUN-only (no private orders).
- No profit guarantee.

## H. Pre-deployment checklist

1. Copy `.env.example` → `.env` on the VPS. Do not commit `.env`.
2. Keep `TRADING_MODE=DRY_RUN` until paper path looks correct in `logs/bot.log`.
3. Confirm public `GET /btc_jpy/candlestick/5min/YYYYMMDD` (JST) if you set
   `CANDLE_TYPE=5min`.
4. Confirm `CANDLE_API_ERROR` is absent and `market_data_real=true`.
5. To go LIVE: keys + `TRADING_MODE=LIVE` +
   `LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK`. Both required.
6. Touch `data/KILL` to halt. One instance (`data/bot.lock`).
7. Watch `WOULD_SUBMIT_ORDER` in LIVE_READY before enabling LIVE.
8. After a LIVE order: `order_id` → UNFILLED/PARTIAL/FULL → balance reconcile.

## Architecture (actual names)

```
main.py / bitbank_bot.main
  → load_config
  → RestClient
  → preflight
  → Engine.run_forever / run_once
      → fetch_candles_detailed (market_data) / CandleCache
      → process_candles → Strategy.evaluate (BUY_GATE/SELL_GATE)
      → evaluate_htf
      → ExecutionGate (via TradeSignalExecutor)
      → RateEngine (FIXED default)
      → PositionSizer / RiskManager
      → OrderExecutor.place  # only create_order caller
      → pending poll / reconcile
      → watchdog / screen
```

## Order path status (code)

| Stage | Status |
| --- | --- |
| Signal | PASS (existing Strategy) |
| Gate | PASS (`ExecutionGate`) |
| DRY_RUN order API | BLOCKED (`ORDER_INTENT` / simulated paper) |
| LIVE_READY order API | BLOCKED (`WOULD_SUBMIT_ORDER`) |
| LIVE dual-auth order API | PASS (`create_order` + `live_confirmed=True`) |
| Fill tracking | PASS (`order_id`, UNFILLED / PARTIAL / FULL) |
| Reconcile | PASS (periodic; Bitbank SoT) |
| Synthetic execute | BLOCKED |
| This VM live POST | NOT_REACHED (safety) |

## Completion vs 100% spec

Honest estimate: **~75%** of the user’s closed-loop spec on the *existing*
architecture. Delivered: candle error path, synthetic ban, modes + dual-auth,
gate, would-submit, no POST retry, fill poll, reconcile, BUY_GATE logs,
FIXED/DYNAMIC/AUTO without collapsing TPs, 5m date keys. Not delivered (on
purpose): new Granville alternatives, invented manager stack, Sentry (not in
repo), iTerm/zsh host integration, live orders from this VM.

## Consistency

- Safety vs prompt: high (dual-auth, no secret logging, synthetic ban kept).
- Architecture vs main: high (Engine / OrderExecutor / RestClient preserved).
- Prior mega-PRs: low on purpose (those added ConnectionManager / ADX regime /
  Sentry / iTerm launchers). This branch stays minimal.

## Strategy catalog (existing only; no new maxims)

BUY1 +3%, BUY2 +5% or +8% golden, BUY3 +4%, BUY4 +5%, SELL1–4, TP, HTF 4h+1d
BUY block. Candidates *not* added this pass: buy-the-dip extras, scoring,
multi-exchange.

---

## Second pass (full-program review)

Review requested after two incomplete pasted diffs. `ReconcileReport` already
had `bitbank_btc`, `local_btc`, `open_orders`, and `mismatches`. The pasted
`market_data.py` hunk had no real change. This pass inspected the existing
program and fixed confirmed bugs only.

### Bugs found and fixed

| Bug | Severity | Fix |
| --- | --- | --- |
| `if active:` treated `{"orders": []}` as open orders; `id → order` maps crashed `.get` | High | `coerce_active_orders()` in RestClient / OrderExecutor / reconcile. Empty dict → no orders. Unknown type raises (refuse live POST). |
| BTC mismatch only when `local > 0` (flat local + Bitbank BTC ignored) | High | Flag when `abs(bitbank_btc - local_btc) > min_amount_btc`. Do not overwrite `state.position` from free BTC. |
| Engine discarded `ReconcileReport` | High | `_apply_reconcile_report`: set `last_block_reason`, clear `pending_missing`, poll `pending_filled_unapplied`. |
| Pending FULLY_FILLED / Bitbank `CANCELED_UNFILLED` never flagged | High | `pending_filled_unapplied` vs `pending_missing` (Bitbank statuses). |
| Candle raise used a redundant `not any(...)` on the same list | Medium | `if not candles and last_error is not None: raise last_error`. |
| Naive / UTC `now` produced wrong YYYYMMDD keys; `lookback_days=0` skipped today | High for 5min | `as_jst()`; `days = max(1, lookback_days)`. |
| REST `data` can be `None` / non-dict; `.get` crashed | Medium | `_as_dict`; JSON payload must be a dict; candlestick first row guarded. |
| ExecutionGate reason `kill_switch_clear` vs risk `kill_switch` | Low | Map failed check to `kill_switch`. |
| `_poll_pending` swallowed balance errors | Low | Log exception type; still use ZERO/ZERO. |

Dataclass fields are populated and consumed (engine + RECONCILE logs). No unused stubs.

### Files changed this pass

**Modified:** `rest_client.py`, `orders.py`, `reconciliation.py`, `engine.py`,
`market_data.py`, `execution_gate.py`, `tests/test_reconciliation.py`,
`tests/test_orders.py`, `tests/test_candle_fetch.py`,
`tests/test_execution_gate.py`, `tests/test_engine.py`,
`tests/test_rest_retry.py`, `reports/closed_loop_audit.md`.

**Added / removed:** none.

### Test results (this pass)

Recorded after `compileall` + `pytest`. Public GET only; no live POST.

---

## Third pass (full-program review)

Review requested after two incomplete pasted diffs. Re-inspected current
sources (did not assume the second-pass summary was still accurate).

**Diff 1:** `ReconcileReport` already has `bitbank_btc`, `local_btc`,
`open_orders`, and `mismatches`. They are populated in `reconcile()` and
read in engine / RECONCILE logs. Not duplicated.

**Diff 2:** `market_data.py` import from `config` is complete and used
(`DEFAULT_MA_PERIOD`, `LONG_CANDLE_TYPES`, `SHORT_CANDLE_TYPES`, `Config`).
The pasted hunk was a no-op.

### Bugs found and fixed

| Bug | Severity | Fix |
| --- | --- | --- |
| `_execute` passed `market_data_real=not used_synthetic_fallback`, so LIVE orders could proceed when `Engine.market_data_real` was still false | High | Pass `self.market_data_real or self._explicit_synthetic` only |
| `--synthetic` `run_forever` merged bars with `real=True`, marking the cache as Bitbank data | High | Do not merge explicit synthetic into `CandleCache` |
| Reconcile compared `free_amount(btc)` to local position, so an open sell (locked BTC) false-mismatched | High | Add open-sell remaining size to free BTC before compare |
| Fill with `executed>0` and `average_price=0` booked a 0-JPY fill and could drop pending | High | Treat missing avg as unfilled pending; poll does not clear until notional exists |
| Heartbeat / `_execute` logged `ORDER MANAGER OK` after `result.ok is False`; `process_candles` logged `MARKET DATA OK` for unverified bars | Medium | DEGRADED / HALTED / UNVERIFIED messages; set `last_block_reason` from failed `OrderResult` |
| `datetime.replace(year=n-1)` raises on 29 Feb for 4h/1d keys (HTF + long candles) | High on leap day | `shift_years()` maps Feb 29 → Feb 28 |
| `drop_incomplete_candle` used wall clock while fetch used injected `now` | Medium | Pass `now_ms` from the fetch clock |
| `RateLimiter.wait` slept while holding the lock (query sleep blocked update) | Medium | Sleep outside the lock |
| `same_entry` used `entry_candle_index`, which shifts when lookback length changes | Medium | Prefer `entry_candle_ts` |
| `save_state` wrote `state.json` in place (crash mid-write can corrupt) | Low | Write `state.json.tmp` then replace |

### Files changed this pass

**Modified:** `engine.py`, `market_data.py`, `multi_timeframe.py`, `orders.py`,
`reconciliation.py`, `rest_client.py`, `strategy.py`,
`tests/test_engine.py`, `tests/test_candle_fetch.py`, `tests/test_orders.py`,
`tests/test_reconciliation.py`, `tests/test_rest_retry.py`,
`tests/test_strategy.py`, `reports/closed_loop_audit.md`.

**Added / removed:** none.

### Test results (this pass)

`python3 -m compileall` PASS. `PYTHONPATH=src pytest` **165 passed**.
Public GET only; no live POST from this VM.

### Remaining risks (honest)

- This pass reviewed the live path in `src/bitbank_bot` and tests. It does
  not claim every possible bug in `run.py`, wiki HTML dumps, or unexercised
  Bitbank payload variants.
- LIVE still needs real keys + confirm phrase on the VPS `.env`.
- HTF 4h+1d still blocks BUY when slopes are down or HTF fetch fails.
- Limit orders can stay UNFILLED; JPY/BTC move after a fill poll.
- Reconcile still uses spot `free_amount` + open *sell* remaining; it does
  not import `onhand_amount` from `/user/assets` (Bitbank field may exist).
- `TradeSignalExecutor` still sets `open_order_conflict=False`; live
  duplicate protection remains in `OrderExecutor.active_orders()`.
- No profit guarantee.

---

## Fourth pass (enhanced launcher)

Existing launchers were `start.sh` (venv + `main.py`), repo-root `main.py`,
stdlib `run.py`, and `python -m bitbank_bot`. This pass enhanced **`start.sh`**
and added `src/bitbank_bot/launch.py` as the recommended wrapper around the
same engine. `run.py` and `python -m bitbank_bot` still work.

`.env.example` already had `RATE_MODE=fixed` and `RECONCILE_EVERY_CYCLES=10`.
`load_config` already maps both into `Config.rate_mode` / `reconcile_every_cycles`
(engine RateEngine + periodic `reconcile()`). Tests now assert that wiring.

Launcher additions (only what `start.sh` lacked):

- Resolve repo root from the script path (no `/Users/kazuteru...` assumption)
- Reuse `.venv`; load `.env` via dotenv without printing values
- Non-secret diagnostics: TRADING_MODE, RATE_MODE, pair `btc_jpy`,
  DRY_RUN/LIVE_READY/LIVE, RECONCILE_EVERY_CYCLES, CANDLE_TYPE, API keys
  SET/UNSET, lock + `data/KILL`, log dir
- LIVE refused unless dual-auth (`TRADING_MODE=LIVE` + confirm phrase + keys);
  otherwise LIVE_READY or DRY_RUN. Default stays DRY_RUN
- Crash restart with backoff; exit 2/3 (config/lock) does not loop
- CLI args still forwarded; `--once` / `--check-config` are one-shot
- `logs/bot.log` uses RotatingFileHandler (5MB × 5)

Start: `bash ./start.sh`. Health: `bash ./start.sh --once --synthetic --skip-lock --no-screen`.

---

## Fifth pass (Mac iTerm zsh paste vs launcher)

### Cause of the Mac output

The iTerm session was in `~` (home), not the repo. The lines

```
........................................................................ [ 80%]
179 passed in 5.34s
zsh: command not found: ...........................
zsh: command not found: 179
```

are pytest progress / summary **pasted into zsh** (or typed after a test run that printed to the TTY). This repo does not emit those strings as shell commands. `start.sh`, `src/bitbank_bot/launch.py`, `main.py`, and `logging_setup.py` were already valid ASCII Python/bash (no U+201C/U+201D smart quotes, no truncated `cfg.`). The follow-on `>` prompt and the snippet with curly quotes (`return f“{path} absent”`) were a **broken chat/paste excerpt**, not the file on disk.

Recovery: press **Ctrl-C** to leave zsh continuation (`>`), then `cd` to the clone and run `bash ./start.sh`. Do not paste pytest output into the terminal.

### Fix (harden; repo sources were already complete)

- `launch.py` refuses cwd outside the repo (`cd to the repo first`) and rejects argv that looks like pytest dots / `[ 40%]` / `passed`. `--help` still works from any directory.
- `start.sh` prints the same recovery text; a copied `start.sh` in `$HOME` or a folder without `src/bitbank_bot/launch.py` exits 2 with that message (no pytest dump).
- Added `scripts/run_bot.sh` (cwd must be the repo; then execs `start.sh`).
- README documents the `zsh: command not found: ....` paste mistake.
- Test: `launch.py` parses via `ast` and contains no smart quotes. RATE_MODE / RECONCILE_EVERY_CYCLES remain wired (config + diagnostics + engine). LIVE stays off by default. No secrets logged.

Enhanced launcher paths: `start.sh`, `src/bitbank_bot/launch.py`, `scripts/run_bot.sh`.

### Test results (this pass)

`python3 -m compileall` PASS. `PYTHONPATH=src pytest` **187 passed**.
`python -m bitbank_bot.launch --help` and `--check-config` PASS from the repo
(RATE_MODE=fixed, RECONCILE_EVERY_CYCLES=10, keys UNSET, DRY_RUN).
From a temp cwd, `--check-config` exits 2 with `cd to the repo first`.
No live POST. No secrets in diagnostics.

---

## Sixth pass (`./start.sh` from ~ and pytest-as-launch)

### Cause of the two Mac messages

1. `bash: ./start.sh: No such file or directory` is **bash**, not the bot.
   `start.sh` is committed on this branch (`git ls-files start.sh` → `start.sh`,
   mode `100755`). It is not on `$PATH` and it is not in `$HOME`. Running
   `./start.sh` from `~` or `/tmp` fails before any repo script runs. A
   checkout that is still `main` without this PR can also lack the enhanced
   launcher (or have an older one). Confirm with `git ls-files start.sh` after
   `git checkout cursor/bitbank-closed-loop-f964`.

2. `PYTHONPATH=src python3 -m pytest -q` was printed in the README Tests
   block (next to a start.sh smoke line). It is **not** a launch command.
   `start.sh`, `launch.py`, and `main.py` do not exec pytest unless
   `--self-test` is explicit. Pasting that line at `~` looks for `src` in
   home and produces confusing errors; pasting pytest dots into zsh is the
   earlier `command not found: ....` class of mistake.

`tests/test_trading_modes.py` was already valid (balanced parens). The
suggested extra `)` after `load_config(...)` was **not** applied.

### Fix

- `scripts/home_start.sh`: home-safe finder. Copy to `~/start.sh` so
  `cd ~ && bash ./start.sh` prints `cd to the repo first` (detects
  `docker-compose-up-d`) instead of a raw missing-file error. Never starts
  the bot. Never runs pytest.
- `scripts/install_launch_alias.sh`: installs that finder and a
  `bitbank-start` function that cds to the clone.
- `scripts/run_tests.sh`: cds to the repo that contains the script, then
  runs pytest. Not a launch step.
- `start.sh --self-test` execs `run_tests.sh` only. Help documents the
  missing-file case and the required branch. Launchers do not print
  `PYTHONPATH=src python3 -m pytest -q`.
- README Start vs Tests split; Mac start is
  `cd ~/docker-compose-up-d && git checkout cursor/bitbank-closed-loop-f964 && bash ./start.sh`.

LIVE stays off. No secrets logged.

### How to start from a Mac

```bash
cd ~/docker-compose-up-d
git checkout cursor/bitbank-closed-loop-f964
git ls-files start.sh
bash ./start.sh
```

### Test results (this pass)

`python3 -m compileall` PASS. `python3 -m py_compile tests/test_trading_modes.py` PASS
(no extra `)`). `PYTHONPATH=src pytest` **195 passed**.
`bash ./start.sh --help` from the repo prints the missing-file recovery and
`--self-test`. After `scripts/home_start.sh` is `./start.sh` in `/tmp` or a
fake `$HOME` (via `install_launch_alias.sh`), `bash ./start.sh` exits 2 with
`cd to the repo first` (not bash's raw missing-file error). No live POST.
No secrets.

---

## Seventh pass (Mac CommandLineTools path + pytest from ~)

### Exact causes (verified)

1. `no tests ran in 1.44s` is pytest started with no `tests/` collection:
   wrong cwd (`~`), or a path that matched nothing. `pytest` / `-q` from home
   does not load this repo's `pyproject.toml` `testpaths = ["tests"]`.
2. `/Library/Developer/CommandLineTools/usr/bin/python3: can't open file ...
   [Errno 2]` is Apple's `/usr/bin/python3` invoked on a missing `.py`
   (often `python3 test_public.py` or `python3 main.py` from `~`, or a
   hardcoded `/Users/.../test_public.py`). It is not a bot crash.
3. `--once` is **not** forwarded on the default `bash ./start.sh` path.
   The leftover comment `# Do not pass --once here.` was removed (docs
   only). The exec line is still
   `exec "$VPY" -m bitbank_bot.launch ... "$@"` with no injected `--once`.
   Default start is the supervised loop, not pytest.

### Fix

- `start.sh` still resolves the repo from `BASH_SOURCE` and `cd`s there, so
  `bash /absolute/path/to/start.sh` from `~` starts the bot. Existing
  `.venv/bin/python` is preferred **before** `pick_python` so CommandLineTools
  python is not used to run the bot when a venv exists. Launch/main/run paths
  are always `$ROOT/...`, never a cwd-relative missing file.
- `resolve_runtime_python(root)` (mockable) prefers `<root>/.venv/bin/python`
  and does not assume cwd.
- `scripts/run_tests.sh` cds to the repo, sets `PYTHONPATH=src`, prefers a
  venv interpreter that has pytest, and collects `tests/` so the result is
  not `no tests ran`. From a foreign cwd, `pytest -p bitbank_bot.pytest_plugin`
  prints `cd to the repo or use: bash scripts/run_tests.sh`.
- README has one Mac execute block: `cd` **or** absolute `start.sh`; do not
  point CommandLineTools python at a random file.

LIVE stays off. No secrets logged. Default `bash ./start.sh` is not
`--once` and is not pytest.

### Test results (this pass)

`python3 -m compileall` PASS. `PYTHONPATH=src pytest` **202 passed**.
`bash /workspace/start.sh --help` from `/tmp` EXIT 0 (locates repo via
BASH_SOURCE). `bash /workspace/start.sh --check-config --no-screen` from
`/tmp` EXIT 0, `project_root=/workspace`,
`using /workspace/.venv/bin/python`, keys UNSET, `may_place_live_orders: False`.
`bash /workspace/scripts/run_tests.sh --collect-only` from `/tmp` collects
`tests/` (not `no tests ran`). `pytest -p bitbank_bot.pytest_plugin` from
`/tmp` EXIT 2 with `cd ... or use: bash .../scripts/run_tests.sh`.
No live POST. No secrets.

---

## Eighth pass (Mac zsh paste + home venv ModuleNotFoundError)

### Exact causes (verified from the Mac paste, not treated as bot crashes)

1. `zsh: command not found: ts:` / `SMOKE_ORDER_OK` / `FAILURE` / `compileall:` /
   `HOW` / `LIVE` / `....` — JSON bot logs, pytest progress, or an agent report
   pasted into interactive zsh at `~`. zsh tried to run those tokens as
   commands. The DRY_RUN JSON (`RATE_DECIDED`, `RISK_CHECK_PASSED`,
   `ORDER_INTENT DRY_RUN`, `SIMULATED_FILL`, `SMOKE_ORDER_OK`, create_order not
   called) is a **successful** dry cycle, not a failure. LIVE stays off.
2. `zsh: event not found: /usr/bin/env` — zsh history expansion on `!` in a
   pasted shebang. `set +H` in `start.sh` cannot disable the *interactive* zsh
   session. Do not paste script source. Usage never prints that shebang.
3. `>` continuation prompt — unclosed quote/JSON from the paste. Ctrl-C.
4. `bash: /workspace/start.sh: No such file or directory` — `/workspace` is the
   cloud VM, not the Mac.
5. `bash: ./run_transaction.sh` / missing
   `/Users/.../docker-compose-up-d/run_transaction.sh` — wrapper was absent;
   this pass adds a 10-line DRY_RUN exec of existing `start.sh`.
6. `ModuleNotFoundError: No module named 'bitbank_bot'` —
   `~/.venv/bin/python -m bitbank_bot.launch` (HOME venv, no `src` on
   sys.path). `start.sh` now refuses any python outside `$ROOT/.venv`, writes
   `bitbank_bot_src.pth` into the **repo** venv, and exports `PYTHONPATH`.
   `launch_bot.py` / `launch.py` insert `src/` from the file location before
   importing `bitbank_bot`.
7. Home finder telling the user to checkout an older `closed-loop-launcher`
   branch — wrong. Every launcher/README string is
   `cursor/bitbank-closed-loop-f964`.

### The one Mac command (cwd may be `~`)

```bash
bash ~/docker-compose-up-d/start.sh
```

Never `bash /workspace/start.sh` on a Mac. Never `~/.venv`.

### Fix

- `start.sh`: `set +H` / `set +o histexpand` for this bash process; refuse
  `$VPY` outside `$ROOT/.venv`; skip `~/.venv` in `pick_python`; write
  `bitbank_bot_src.pth`; keep `PYTHONPATH=$ROOT/src`; usage tells users not to
  paste JSON/agent/script source.
- `run_transaction.sh`: `cd` via `BASH_SOURCE`, then
  `exec bash "$ROOT/start.sh" --once --skip-lock --no-screen`.
- `launch_bot.py`: sys.path `src`, then `bitbank_bot.launch.main`; refuses
  `~/.venv`.
- `scripts/home_start.sh` / `install_launch_alias.sh` / README: correct branch
  and the one-command recovery line.

LIVE stays off. No secrets logged. No live POST.

### Test results (this pass)

Recorded after `compileall` + pytest on this branch.

