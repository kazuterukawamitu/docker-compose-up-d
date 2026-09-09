from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from bitbank_bot.market_data import synthetic_candles
from bitbank_bot.risk import RiskManager
from bitbank_bot.strategy import Signal
from bitbank_bot.trade_signal_executor import TradeSignalExecutor
from tests.helpers import cfg


def test_dry_run_pipeline_simulates() -> None:
    c = cfg(dry_run=True, live_trading=False, simulate_fill=True)
    client = MagicMock()
    client.create_order.side_effect = AssertionError("live")
    exe = TradeSignalExecutor(c, client)
    out = exe.run(
        signal=Signal("BUY1", "buy", Decimal("0.03"), "t"),
        price=Decimal("10000000"),
        candles=synthetic_candles(40),
        available_jpy=Decimal("100000"),
        available_btc=Decimal("0"),
        risk=RiskManager(c),
        market_data_real=True,
        market_data_fresh=True,
        connection=None,
        private_api_ok=True,
        kill_switch=False,
        pending_order=False,
    )
    assert out.order is not None
    assert out.order.simulated
    client.create_order.assert_not_called()


def test_live_ready_does_not_post() -> None:
    c = cfg(dry_run=False, live_trading=False, trading_mode="LIVE_READY")
    client = MagicMock()
    exe = TradeSignalExecutor(c, client)
    out = exe.run(
        signal=Signal("BUY1", "buy", Decimal("0.03"), "t"),
        price=Decimal("10000000"),
        candles=synthetic_candles(40),
        available_jpy=Decimal("100000"),
        available_btc=Decimal("0"),
        risk=RiskManager(c),
        market_data_real=True,
        market_data_fresh=True,
        connection=None,
        private_api_ok=True,
        kill_switch=False,
        pending_order=False,
    )
    assert out.blocked
    assert out.block_reason == "live_ready"
    assert out.order is not None
    assert out.order.reason == "would_submit"
    client.create_order.assert_not_called()
