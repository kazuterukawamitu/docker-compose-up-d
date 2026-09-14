# Master requirements (synthesized)

This file is the single specification taken from the combined
END OF PROMPT requests. Contradictions are resolved here; they are
not implemented twice.

## Treated as correct

1. Bitbank only. Pair internally and on the API is `btc_jpy`.
2. Do not rewrite the bot from scratch. Keep README MA strategy BUY1–4 / SELL1–4 percents.
3. Default remains `DRY_RUN`. Dual-auth is required for LIVE:
   `TRADING_MODE=LIVE` and `LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK`
   plus API keys. Missing either LIVE flag becomes `LIVE_READY`
   (`WOULD_SUBMIT_ORDER`, no POST).
4. When README BUY/SELL conditions match and the execution gate is
   open, the order path must complete: paper `SIMULATED_FILL` in
   DRY_RUN, `WOULD_SUBMIT_ORDER` in LIVE_READY, `create_order` only
   in dual-confirmed LIVE. Extra SIGNAL_ONLY / silent HOLD is not a
   second kill switch.
5. Synthetic / accidental fallback candles never live-order.
6. One order POST path: Strategy → RateEngine → Risk/Sizer →
   ExecutionGate → OrderExecutor → Bitbank. Strategies never call
   `create_order`.
7. Enhanced launcher is `start.sh` → `python -m bitbank_bot.launch`.
8. Output-program count vs `origin/main` must be disclosed at launch.

## Treated as incorrect / not implemented as written

- Enabling LIVE by flipping only `DRY_RUN=false`.
- Auto-rewriting Python source at runtime (“self-healing” of code).
- Adding Granville/RSI/MACD/ADX/Sakata as new parallel strategies
  that AND together into perpetual HOLD. Existing README MA rules
  stay the SignalEngine.
- Placing real-money orders from tests or from this cloud agent.
- SSH install of systemd on the user’s VPS.

## Architecture (actual)

MarketData (REST + optional WS)
→ Strategy (README MA)
→ RateEngine (FIXED / DYNAMIC / AUTO)
→ RiskManager + PositionSizer
→ ExecutionGate
→ OrderExecutor (only `create_order` caller)
→ Fill poll (`state.pending`)
→ ReconciliationManager (Bitbank as source of truth)
→ TradingScreen / logs/bot.log
