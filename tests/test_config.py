import pytest

from bitbank_bot.config import (
    DEFAULT_LOCK_PATH,
    DEFAULT_LONG_MA_PERIOD,
    DEFAULT_MA_PERIOD,
    DEFAULT_SHORT_MA_PERIOD,
    Config,
    ConfigError,
    load_config,
)
from bitbank_bot.money import D


def test_master_policy_defaults_match_dataclass() -> None:
    empty = load_config(
        load_default_dotenv=False,
        environ={"DRY_RUN": "true", "LIVE_TRADING": "false"},
    )
    baked = Config()
    assert empty.ma_period == DEFAULT_MA_PERIOD == baked.ma_period == 20
    assert empty.short_ma_period == DEFAULT_SHORT_MA_PERIOD == baked.short_ma_period == 20
    assert empty.long_ma_period == DEFAULT_LONG_MA_PERIOD == baked.long_ma_period == 50
    assert empty.ma_slope_threshold == baked.ma_slope_threshold == D("0.0005")
    assert empty.candle_type == baked.candle_type == "1hour"
    assert empty.lock_path == baked.lock_path == DEFAULT_LOCK_PATH
    assert empty.stale_ws_sec == baked.stale_ws_sec == 60.0
    assert empty.daily_pnl_floor == baked.daily_pnl_floor == D("150")
    assert empty.wiki_cross_rules is False
    assert empty.mtf_filter is False


def test_rejected_pair_alias() -> None:
    with pytest.raises(ConfigError):
        load_config(
            load_default_dotenv=False,
            environ={"BITBANK_PAIR": "btc_jpn", "DRY_RUN": "true", "LIVE_TRADING": "false"},
        )


def test_pair_must_be_btc_jpy() -> None:
    with pytest.raises(ConfigError):
        load_config(
            load_default_dotenv=False,
            environ={"BITBANK_PAIR": "xrp_jpy", "DRY_RUN": "true", "LIVE_TRADING": "false"},
        )


def test_live_requires_keys() -> None:
    with pytest.raises(ConfigError):
        load_config(
            load_default_dotenv=False,
            environ={"DRY_RUN": "false", "LIVE_TRADING": "true"},
        )


def test_dry_run_false_requires_live_flag() -> None:
    with pytest.raises(ConfigError):
        load_config(
            load_default_dotenv=False,
            environ={"DRY_RUN": "false", "LIVE_TRADING": "false"},
        )
