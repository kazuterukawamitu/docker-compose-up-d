from __future__ import annotations

from decimal import Decimal

from bitbank_bot.amounts import plan_buy
from bitbank_bot.market_data import synthetic_candles
from bitbank_bot.strategy import Signal
from bitbank_bot.trade_signal_executor import TradeSignalExecutor
from tests.helpers import cfg, risk


class _ConflictClient:
    def __init__(self, orders: list[dict[str, object]]) -> None:
        self._orders = orders

    def get_active_orders(self, pair: str) -> list[dict[str, object]]:
        assert pair == "btc_jpy"
        return list(self._orders)


def test_submit_blocks_when_bitbank_has_open_orders() -> None:
    c = cfg()
    r = risk(c)
    plan = plan_buy(
        available_jpy=Decimal("100000"),
        available_btc=Decimal("0"),
        price=Decimal("10000000"),
        cfg=c,
        risk=r,
    )
    executor = TradeSignalExecutor(
        c, r, _ConflictClient([{"order_id": "1", "side": "buy", "status": "UNFILLED"}])
    )
    outcome = executor.submit(
        Signal("BUY1", "buy", Decimal("0.03"), "t"),
        plan,
        synthetic_candles(40),
        market_data_real=True,
        market_data_fresh=True,
        kill_switch=False,
        pending_order=False,
        ws_stale=False,
        explicit_synthetic=True,
    )
    assert outcome.result is None
    assert outcome.blocked == "open_order_conflict"


def test_submit_reaches_order_executor_on_matching_buy() -> None:
    c = cfg()
    r = risk(c)
    plan = plan_buy(
        available_jpy=Decimal("100000"),
        available_btc=Decimal("0"),
        price=Decimal("10000000"),
        cfg=c,
        risk=r,
    )
    executor = TradeSignalExecutor(c, r, None)
    outcome = executor.submit(
        Signal("BUY1", "buy", Decimal("0.03"), "t"),
        plan,
        synthetic_candles(40),
        market_data_real=True,
        market_data_fresh=True,
        kill_switch=False,
        pending_order=False,
        ws_stale=False,
        explicit_synthetic=True,
        open_order_conflict=False,
    )
    assert outcome.blocked == ""
    assert outcome.result is not None
    assert outcome.result.ok
    assert outcome.result.reason == "simulated"
