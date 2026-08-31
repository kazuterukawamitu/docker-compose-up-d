from bitbank_bot.indicators import (
    IncrementalSMA,
    Trend,
    atr,
    bollinger,
    crossed_down,
    crossed_up,
    crossover_price_bp,
    ema,
    interpolate_crossover,
    is_dead_cross,
    is_golden_cross,
    ma_trend,
    macd,
    rsi,
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
    assert crossover_price_bp(price) == D("1")


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


def test_dead_cross_is_event_not_state() -> None:
    assert is_dead_cross(D("11"), D("10"), D("9"), D("10"))
    assert not is_dead_cross(D("9"), D("10"), D("8"), D("10"))


def test_ma_trend_threshold() -> None:
    th = D("0.01")
    assert ma_trend(D("102"), D("100"), th) == Trend.UP
    assert ma_trend(D("98"), D("100"), th) == Trend.DOWN
    assert ma_trend(D("100.5"), D("100"), th) == Trend.FLAT


def test_incremental_sma_matches_batch() -> None:
    values = [D("1"), D("2"), D("3"), D("4"), D("5")]
    batch = sma(values, 3)
    inc = IncrementalSMA(3)
    out = [inc.update(v) for v in values]
    assert out == batch


def test_rsi_bounds() -> None:
    rising = [D(i) for i in range(1, 30)]
    out = rsi(rising, 14)
    last = out[-1]
    assert last is not None
    assert last > D("70")
    flat = [D("10")] * 20
    flat_rsi = rsi(flat, 14)
    assert flat_rsi[-1] == D("50")


def test_macd_histogram_defined() -> None:
    values = [D(i) for i in range(1, 50)]
    line, signal, hist = macd(values)
    assert len(line) == len(values) == len(signal) == len(hist)
    assert any(x is not None for x in hist)


def test_atr_and_bollinger() -> None:
    highs = [D("11"), D("12"), D("13"), D("14"), D("15")]
    lows = [D("9"), D("10"), D("11"), D("12"), D("13")]
    closes = [D("10"), D("11"), D("12"), D("13"), D("14")]
    out = atr(highs, lows, closes, 3)
    assert out[-1] is not None
    mid, upper, lower = bollinger(closes, 3, D("2"))
    assert mid[-1] is not None
    assert upper[-1] is not None and lower[-1] is not None
    assert upper[-1] >= mid[-1] >= lower[-1]
