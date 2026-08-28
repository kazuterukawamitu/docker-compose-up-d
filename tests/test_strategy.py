from decimal import Decimal

from bitbank_bot.models import Position
from bitbank_bot.strategy.ma_rules import MaRuleStrategy, PreparedBar
from tests.conftest import make_settings


def _bar(**kwargs: object) -> PreparedBar:
    base = dict(
        ts=1,
        close=Decimal("100"),
        ma=Decimal("100"),
        ema_fast=Decimal("100"),
        ema_slow=Decimal("99"),
        slope="up",
        golden_cross_event=False,
        death_cross_event=False,
    )
    base.update(kwargs)
    return PreparedBar(**base)  # type: ignore[arg-type]


def _strat() -> MaRuleStrategy:
    return MaRuleStrategy(make_settings())


def test_buy_1_ma_turns_and_crosses_up() -> None:
    strat = _strat()
    strat.memory.ma_was_down = True
    strat.memory.last_close = Decimal("99")
    strat.memory.last_ma = Decimal("100")
    signal = strat._signal_for(_bar(close=Decimal("102"), ma=Decimal("100"), slope="flat"), Position())
    assert signal.action == "BUY"
    assert signal.rule_id == "buy_1"
    assert signal.take_profit_pct == Decimal("0.03")


def test_buy_2_uptrend_cross_down_golden_cross_tp() -> None:
    strat = _strat()
    strat.memory.last_close = Decimal("101")
    strat.memory.last_ma = Decimal("100")
    strat.memory.golden_cross_regime = True
    signal = strat._signal_for(_bar(close=Decimal("99"), ma=Decimal("100"), slope="up"), Position())
    assert signal.action == "BUY"
    assert signal.rule_id == "buy_2"
    assert signal.take_profit_pct == Decimal("0.08")


def test_buy_2_without_golden_cross_uses_5pct() -> None:
    strat = _strat()
    strat.memory.last_close = Decimal("101")
    strat.memory.last_ma = Decimal("100")
    strat.memory.golden_cross_regime = False
    signal = strat._signal_for(
        _bar(close=Decimal("99"), ma=Decimal("100"), slope="up", ema_fast=Decimal("90"), ema_slow=Decimal("100")),
        Position(),
    )
    assert signal.take_profit_pct == Decimal("0.05")


def test_buy_3_bounce_above_ma() -> None:
    strat = _strat()
    strat.memory.last_close = Decimal("104")
    strat.memory.last_ma = Decimal("100")
    strat.memory.extended_plus_5 = True
    strat.memory.declined_from_plus_5 = True
    signal = strat._signal_for(_bar(close=Decimal("106"), ma=Decimal("100"), slope="up"), Position())
    assert signal.rule_id == "buy_3"
    assert signal.take_profit_pct == Decimal("0.04")


def test_buy_4_bounce_below_declining_ma() -> None:
    strat = _strat()
    strat.memory.last_close = Decimal("90")
    strat.memory.last_ma = Decimal("100")
    strat.memory.extended_minus_5_down_ma = True
    signal = strat._signal_for(_bar(close=Decimal("92"), ma=Decimal("100"), slope="down"), Position())
    assert signal.rule_id == "buy_4"
    assert signal.take_profit_pct == Decimal("0.05")


def test_sell_rules_require_open_position() -> None:
    strat = _strat()
    strat.memory.last_close = Decimal("105")
    strat.memory.last_ma = Decimal("100")
    strat.memory.extended_plus_5 = True
    signal = strat._signal_for(_bar(close=Decimal("104"), ma=Decimal("100"), slope="up"), Position())
    assert signal.action != "SELL"


def test_sell_5_after_plus_4_then_decline() -> None:
    strat = _strat()
    strat.memory.last_close = Decimal("106")
    strat.memory.last_ma = Decimal("100")
    position = Position(amount=Decimal("0.001"), entry_price=Decimal("100"), take_profit_pct=Decimal("0.10"), bars_held=2)
    signal = strat._signal_for(_bar(close=Decimal("105"), ma=Decimal("100"), slope="up"), position)
    assert signal.rule_id == "sell_5"


def test_sell_6_cross_down_and_decline() -> None:
    strat = _strat()
    strat.memory.last_close = Decimal("101")
    strat.memory.last_ma = Decimal("100")
    position = Position(amount=Decimal("0.001"), entry_price=Decimal("100"), take_profit_pct=Decimal("0.50"), bars_held=2)
    signal = strat._signal_for(_bar(close=Decimal("99"), ma=Decimal("100"), slope="down"), position)
    assert signal.rule_id == "sell_6"


def test_sell_7_cross_up_declining_ma() -> None:
    strat = _strat()
    strat.memory.last_close = Decimal("99")
    strat.memory.last_ma = Decimal("100")
    position = Position(amount=Decimal("0.001"), entry_price=Decimal("100"), take_profit_pct=Decimal("0.50"), bars_held=2)
    signal = strat._signal_for(_bar(close=Decimal("101"), ma=Decimal("100"), slope="down"), position)
    assert signal.rule_id == "sell_7"


def test_sell_8_failed_rally_below_ma() -> None:
    strat = _strat()
    strat.memory.last_close = Decimal("97")
    strat.memory.last_ma = Decimal("100")
    strat.memory.rose_from_minus_4 = True
    position = Position(amount=Decimal("0.001"), entry_price=Decimal("100"), take_profit_pct=Decimal("0.50"), bars_held=2)
    signal = strat._signal_for(_bar(close=Decimal("96"), ma=Decimal("100"), slope="down"), position)
    assert signal.rule_id == "sell_8"


def test_take_profit_hits_before_other_sells() -> None:
    strat = _strat()
    strat.memory.last_close = Decimal("100")
    strat.memory.last_ma = Decimal("100")
    position = Position(
        amount=Decimal("0.001"),
        entry_price=Decimal("100"),
        take_profit_pct=Decimal("0.03"),
        bars_held=2,
        rule_id="buy_1",
    )
    signal = strat._signal_for(_bar(close=Decimal("104"), ma=Decimal("100"), slope="up"), position)
    assert signal.rule_id == "take_profit"


def test_same_bar_does_not_repeat_entry() -> None:
    from bitbank_bot.market.candles import synthetic_trend

    strat = _strat()
    candles = synthetic_trend(Decimal("100"), [Decimal("-1")] * 20 + [Decimal("0"), Decimal("0"), Decimal("8")])
    strat.evaluate(candles, Position())
    second = strat.evaluate(candles, Position())
    assert second.action == "HOLD"


def test_wiki_golden_cross_off_by_default() -> None:
    strat = _strat()
    strat.memory.last_close = Decimal("100")
    strat.memory.last_ma = Decimal("100")
    strat.memory.last_fast = Decimal("90")
    signal = strat._signal_for(
        _bar(close=Decimal("100"), ma=Decimal("100"), slope="up", golden_cross_event=True, ema_fast=Decimal("101"), ema_slow=Decimal("99")),
        Position(),
    )
    assert signal.rule_id != "wiki_golden_cross"


def test_wiki_golden_cross_buy_when_enabled() -> None:
    strat = MaRuleStrategy(make_settings(wiki_cross_rules=True))
    strat.memory.last_close = Decimal("100")
    strat.memory.last_ma = Decimal("100")
    strat.memory.last_fast = Decimal("90")
    signal = strat._signal_for(
        _bar(close=Decimal("100"), ma=Decimal("100"), slope="up", golden_cross_event=True, ema_fast=Decimal("101"), ema_slow=Decimal("99")),
        Position(),
    )
    assert signal.action == "BUY"
    assert signal.rule_id == "wiki_golden_cross"
    assert signal.take_profit_pct == Decimal("0.03")


def test_wiki_death_cross_sell_when_enabled() -> None:
    strat = MaRuleStrategy(make_settings(wiki_cross_rules=True))
    strat.memory.last_close = Decimal("100")
    strat.memory.last_ma = Decimal("100")
    strat.memory.last_fast = Decimal("101")
    position = Position(amount=Decimal("0.001"), entry_price=Decimal("100"), take_profit_pct=Decimal("0.50"), bars_held=2)
    signal = strat._signal_for(
        _bar(
            close=Decimal("100"),
            ma=Decimal("100"),
            slope="flat",
            death_cross_event=True,
            ema_fast=Decimal("99"),
            ema_slow=Decimal("100"),
        ),
        position,
    )
    assert signal.action == "SELL"
    assert signal.rule_id == "wiki_death_cross"
