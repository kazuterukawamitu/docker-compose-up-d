import pytest

from bitbank_bot.config import ConfigError, load_config


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
