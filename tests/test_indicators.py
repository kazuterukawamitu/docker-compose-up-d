from bitbank_bot.indicators import (
    Trend,
    crossed_down,
    crossed_up,
    ema,
    interpolate_crossover,
    is_golden_cross,
    ma_trend,
    sma,
)
from bitbank_bot.money import D


def test_sma() -> None:
    values = [D("1"), D("2"), D("3"), D("4")]
    out = sma(values, 3)
    assert out[0] is None
    assert out[1] is None
    assert out[2] == D("2")
    assert out[3] == D("3")


def test_ema_seeds_from_sma() -> None:
    values = [D("1"), D("2"), D("3"), D("4")]
    out = ema(values, 3)
    assert out[0] is None
    assert out[1] is None
    assert out[2] == D("2")
    assert out[3] is not None
    assert out[3] > D("2")


def test_crossover_interpolation() -> None:
    price = interpolate_crossover(D("90"), D("100"), D("110"), D("100"))
    assert price == D("100")


def test_crossover_interpolation_out_of_range() -> None:
    assert interpolate_crossover(D("90"), D("80"), D("95"), D("81")) is None


def test_cross_flags() -> None:
    assert crossed_up(D("99"), D("100"), D("101"), D("100"))
    assert crossed_down(D("101"), D("100"), D("99"), D("100"))
    assert not crossed_up(D("101"), D("100"), D("102"), D("100"))


def test_golden_cross_is_event_not_state() -> None:
    assert is_golden_cross(D("9"), D("10"), D("11"), D("10"))
    assert not is_golden_cross(D("11"), D("10"), D("12"), D("10"))
    assert not is_golden_cross(D("9"), D("10"), D("9.5"), D("10"))


def test_ma_trend_threshold() -> None:
    th = D("0.01")
    assert ma_trend(D("102"), D("100"), th) == Trend.UP
    assert ma_trend(D("98"), D("100"), th) == Trend.DOWN
    assert ma_trend(D("100.5"), D("100"), th) == Trend.FLAT
