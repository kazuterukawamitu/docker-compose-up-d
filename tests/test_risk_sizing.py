from decimal import Decimal

from bitbank_bot.models import Signal, Snapshot, Ticker, Position
from bitbank_bot.orders.sizing import plan_size
from bitbank_bot.risk.manager import RiskManager
from tests.conftest import make_settings


def _snapshot(**kwargs: object) -> Snapshot:
    ticker = Ticker(last=Decimal("10000000"), buy=Decimal("9999999"), sell=Decimal("10000001"), timestamp_ms=kwargs.pop("now_ms", 1_000_000))  # type: ignore[misc]
    base = dict(
        candles=[],
        ticker=ticker,
        position=Position(),
        jpy_free=Decimal("1000000"),
        btc_free=Decimal("0.01"),
        circuit_mode="NONE",
        ws_ok=True,
        now_ms=ticker.timestamp_ms,
    )
    base.update(kwargs)
    return Snapshot(**base)  # type: ignore[arg-type]


def test_min_unit_buy_size() -> None:
    settings = make_settings()
    signal = Signal(action="BUY", rule_id="buy_1", reason="x", take_profit_pct=Decimal("0.03"), target_kind="min_unit")
    plan = plan_size(settings, signal, _snapshot())
    assert plan.planned == Decimal("0.0001")
    assert plan.blocked == ""


def test_max_available_buy_respects_jpy_and_cap() -> None:
    settings = make_settings(order_size_mode="max_available", max_position_btc=Decimal("0.002"))
    signal = Signal(action="BUY", rule_id="buy_1", reason="x", target_kind="max_available")
    plan = plan_size(settings, signal, _snapshot(jpy_free=Decimal("50000")))
    # 50000 * 0.99 / 10000001 ≈ 0.0049, capped at 0.002
    assert plan.planned == Decimal("0.002")


def test_insufficient_jpy_blocks_min_unit() -> None:
    settings = make_settings()
    signal = Signal(action="BUY", rule_id="buy_1", reason="x", target_kind="min_unit")
    plan = plan_size(settings, signal, _snapshot(jpy_free=Decimal("1")))
    assert plan.planned == 0
    assert "insufficient" in plan.blocked


def test_risk_blocks_stale_data(tmp_path) -> None:
    settings = make_settings(tmp_path=tmp_path, stale_ms=100)
    risk = RiskManager(settings)
    snap = _snapshot(now_ms=10_000)
    snap.ticker = Ticker(last=Decimal("1"), buy=Decimal("1"), sell=Decimal("1"), timestamp_ms=1)
    decision = risk.check(Signal(action="BUY", rule_id="buy_1", reason="x"), snap, Decimal("0"), Decimal("0"))
    assert not decision.allowed
    assert "stale" in decision.reason


def test_risk_kill_file(tmp_path) -> None:
    settings = make_settings(tmp_path=tmp_path)
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    (settings.state_dir / "KILL").write_text("1", encoding="utf-8")
    risk = RiskManager(settings)
    decision = risk.check(Signal(action="SELL", rule_id="sell_5", reason="x"), _snapshot(), Decimal("0"), Decimal("0"))
    assert not decision.allowed


def test_daily_loss_cap(tmp_path) -> None:
    settings = make_settings(tmp_path=tmp_path, max_daily_loss_jpy=Decimal("10"))
    risk = RiskManager(settings)
    decision = risk.check(
        Signal(action="BUY", rule_id="buy_1", reason="x"),
        _snapshot(),
        Decimal("-11"),
        Decimal("-11"),
    )
    assert "daily loss" in decision.reason
