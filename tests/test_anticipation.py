from __future__ import annotations

from decimal import Decimal

from bitbank_bot.anticipation import HazardAssessment, anticipate_hazard
from bitbank_bot.engine import Engine, load_state
from bitbank_bot.indicators import Trend, close_returns
from bitbank_bot.money import D
from bitbank_bot.strategy import MarketSnapshot, Signal
from tests.helpers import cfg
from tests.test_engine import FakeRest


def _snap(**overrides: object) -> MarketSnapshot:
    base = dict(
        index=10,
        timestamp_ms=10,
        close=D("105"),
        prev_close=D("106"),
        ma=D("100"),
        prev_ma=D("100.1"),
        short_ma=D("101"),
        prev_short_ma=D("102"),
        long_ma=D("103"),
        prev_long_ma=D("102"),
        ma_trend=Trend.DOWN,
        prev_ma_trend=Trend.DOWN,
        crossed_up=False,
        crossed_down=False,
        golden_cross=False,
        dead_cross=True,
        cross_price=None,
    )
    base.update(overrides)
    return MarketSnapshot(**base)  # type: ignore[arg-type]


def test_hazard_never_claims_certain_future() -> None:
    c = cfg()
    assessment = anticipate_hazard(
        _snap(),
        cfg=c,
        entropy=D("0.9"),
        daily_pnl=D("-50"),
        htf_down=True,
        returns=close_returns([D("100") + D(i) for i in range(21)]),
    )
    assert assessment.probability <= D("0.99")
    assert assessment.confidence <= D("0.95")
    assert assessment.probability < D("1")
    assert "look_ahead" not in assessment.reasons


def test_hazard_uses_only_supplied_present_returns() -> None:
    c = cfg()
    known = [D("100"), D("101"), D("102")]
    future_crash = [D("40")]
    now = anticipate_hazard(
        _snap(close=D("102"), prev_close=D("101"), ma=D("100"), dead_cross=False),
        cfg=c,
        entropy=D("0.2"),
        daily_pnl=D("0"),
        htf_down=False,
        returns=close_returns(known),
    )
    later = anticipate_hazard(
        _snap(close=D("40"), prev_close=D("102"), ma=D("100"), dead_cross=True),
        cfg=c,
        entropy=D("0.9"),
        daily_pnl=D("-500"),
        htf_down=True,
        returns=close_returns(known + future_crash),
    )
    assert now.probability < later.probability


def test_high_entropy_alone_does_not_veto_or_force_buy() -> None:
    c = cfg(ky_veto_probability=D("0.85"))
    assessment = anticipate_hazard(
        _snap(
            close=D("100"),
            prev_close=D("100"),
            ma=D("100"),
            ma_trend=Trend.FLAT,
            prev_ma_trend=Trend.FLAT,
            dead_cross=False,
        ),
        cfg=c,
        entropy=D("0.95"),
        daily_pnl=D("0"),
        htf_down=False,
        returns=[D("0.01"), D("-0.01"), D("0.02")] * 8,
    )
    assert "high_entropy_uncertain" in assessment.reasons
    assert assessment.veto is False
    assert assessment.probability < c.ky_veto_probability


def test_veto_blocks_buy_in_engine(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        dry_run=True,
        live_trading=False,
    )
    rest = FakeRest()
    engine = Engine(c, client=rest)  # type: ignore[arg-type]
    state = load_state(c.state_path, c)
    engine._last_hazard = HazardAssessment(
        probability=D("0.9"),
        confidence=D("0.8"),
        veto=True,
        reasons=("ky_veto",),
    )
    engine._execute(
        Signal("BUY1", "buy", Decimal("0.03"), "forced"),
        Decimal("10000000"),
        1,
        1,
        state,
    )
    assert rest.create_order_calls == 0
    assert engine.last_block_reason == "ky_veto"
    assert state.position is None
