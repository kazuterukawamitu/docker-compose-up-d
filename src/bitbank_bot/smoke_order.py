"""DRY_RUN paper-order smoke. Proves the launcher can reach OrderExecutor.

Never calls Bitbank POST. Refuses when LIVE dual-auth is armed.
"""

from __future__ import annotations

from bitbank_bot.amounts import PositionSizer
from bitbank_bot.config import MODE_DRY_RUN, RATE_MODE_FIXED, Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.market_data import synthetic_candles
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import Signal
from bitbank_bot.trade_signal_executor import TradeSignalExecutor


def run_smoke_order(cfg: Config) -> int:
    """Drive one BUY through the real order path as a paper fill."""
    if cfg.may_place_live_orders:
        slog("ERROR", "refusing --smoke-order while LIVE (would be real money)")
        print("SMOKE_ORDER_FAIL LIVE_REFUSED")
        return 2
    cfg.dry_run = True
    cfg.live_trading = False
    cfg.trading_mode = MODE_DRY_RUN
    cfg.live_trading_confirm = False
    cfg.simulate_fill = True
    cfg.rate_mode = RATE_MODE_FIXED
    candles = synthetic_candles(40)
    price = candles[-1].close
    risk = RiskManager(cfg)
    sizer = PositionSizer(cfg, risk)
    plan = sizer.plan_buy(
        available_jpy=cfg.dry_run_free_jpy,
        available_btc=cfg.dry_run_free_btc,
        price=price,
    )
    slog(
        "SMOKE_ORDER",
        "paper BUY through TradeSignalExecutor",
        amount=str(plan.amount),
        price=str(price),
        plan_ok=plan.ok,
        may_place_live_orders=cfg.may_place_live_orders,
    )
    executor = TradeSignalExecutor(cfg, risk, None)
    signal = Signal(kind="BUY1", side="buy", tp_pct=cfg.buy1_tp, reason="smoke_order")
    outcome = executor.submit(
        signal,
        plan,
        candles,
        market_data_real=True,
        market_data_fresh=True,
        kill_switch=False,
        pending_order=False,
        ws_stale=False,
        explicit_synthetic=True,
        open_order_conflict=False,
    )
    result = outcome.result
    if outcome.blocked:
        slog("ERROR", "smoke-order gated", reason=outcome.blocked)
        print(f"SMOKE_ORDER_FAIL gated={outcome.blocked}")
        return 2
    if result is None or not result.ok or result.reason != "simulated":
        reason = result.reason if result is not None else "no_result"
        slog("ERROR", "smoke-order did not simulate a fill", reason=reason)
        print(f"SMOKE_ORDER_FAIL reason={reason}")
        return 2
    if result.executed_amount <= 0:
        slog("ERROR", "smoke-order simulated fill had zero amount")
        print("SMOKE_ORDER_FAIL zero_fill")
        return 2
    slog(
        "SIMULATED_FILL",
        "smoke-order paper fill",
        executed_amount=str(result.executed_amount),
        average_price=str(result.average_price),
        create_order_called=False,
    )
    print(
        "SMOKE_ORDER_OK SIMULATED_FILL "
        f"amount={result.executed_amount} price={result.average_price}"
    )
    return 0
