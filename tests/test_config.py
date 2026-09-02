from __future__ import annotations

from decimal import Decimal

import pytest

from bitbank_bot.config import PAIR, ConfigError, load_config, normalize_pair


def test_default_is_dry_run() -> None:
    cfg = load_config(environ={}, load_default_dotenv=False)
    assert cfg.dry_run is True
    assert cfg.live_trading is False
    assert cfg.may_place_live_orders is False
    assert cfg.daily_pnl_floor == Decimal("0")
    assert cfg.pair == PAIR
    assert "secret" not in cfg.safe_dict()
    assert cfg.safe_dict()["has_api_secret"] is False


def test_pair_normalize_and_reject() -> None:
    assert normalize_pair("BTC/JPY") == "btc_jpy"
    with pytest.raises(ConfigError, match="btc_jpy"):
        load_config(environ={"BITBANK_PAIR": "eth_jpy"}, load_default_dotenv=False)
    with pytest.raises(ConfigError, match="rejected"):
        load_config(environ={"BITBANK_PAIR": "btcjpy"}, load_default_dotenv=False)


def test_dual_flag_required_for_live() -> None:
    with pytest.raises(ConfigError, match="dual confirmation"):
        load_config(environ={"DRY_RUN": "false"}, load_default_dotenv=False)
    with pytest.raises(ConfigError, match="cannot both"):
        load_config(
            environ={"DRY_RUN": "true", "LIVE_TRADING": "true"},
            load_default_dotenv=False,
        )
    with pytest.raises(ConfigError, match="requires BITBANK_API"):
        load_config(
            environ={"DRY_RUN": "false", "LIVE_TRADING": "true"},
            load_default_dotenv=False,
        )


def test_balance_usage_alias() -> None:
    cfg = load_config(
        environ={"BALANCE_USAGE_RATIO": "0.8"}, load_default_dotenv=False
    )
    assert str(cfg.max_balance_usage) == "0.8"


def test_repr_hides_secret() -> None:
    cfg = load_config(
        environ={"BITBANK_API_KEY": "k", "BITBANK_API_SECRET": "s" * 16},
        load_default_dotenv=False,
    )
    text = repr(cfg)
    assert "s" * 16 not in text
    assert cfg.api_secret == "s" * 16
