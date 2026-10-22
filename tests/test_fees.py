from __future__ import annotations

from decimal import Decimal

from bitbank_bot.fees import (
    expected_net_jpy,
    fee_allows_target,
    fill_fee_jpy,
    incremental_notional,
    round_trip_cost_rate,
)


def test_incremental_notional_uses_the_new_price() -> None:
    delta_qty, delta_notional, incremental_avg = incremental_notional(
        Decimal("0.0004"),
        Decimal("10000000"),
        Decimal("0.0007"),
        Decimal("7300") / Decimal("0.0007"),
    )
    assert delta_qty == Decimal("0.0003")
    assert delta_notional == Decimal("3300")
    assert incremental_avg == Decimal("11000000")


def test_first_fill_matches_qty_times_average() -> None:
    delta_qty, delta_notional, incremental_avg = incremental_notional(
        Decimal("0"),
        Decimal("0"),
        Decimal("0.001"),
        Decimal("10000000"),
    )
    assert delta_qty == Decimal("0.001")
    assert delta_notional == Decimal("10000")
    assert incremental_avg == Decimal("10000000")


def test_round_trip_taker_beats_a_small_scalp() -> None:
    rate = round_trip_cost_rate(Decimal("0.0012"))
    assert rate == Decimal("0.0024")
    assert fee_allows_target(Decimal("0.03"), rate) is True
    assert fee_allows_target(Decimal("0.0005"), rate) is False
    small = expected_net_jpy(Decimal("10000"), Decimal("0.0005"), Decimal("0.0012"))
    wide = expected_net_jpy(Decimal("10000"), Decimal("0.03"), Decimal("0.0012"))
    assert small < 0
    assert wide > 0
    assert fill_fee_jpy(Decimal("10000"), Decimal("0.0012")) == Decimal("12")
