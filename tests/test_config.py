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
    assert cfg.enable_htf_filter is True
    assert "secret" not in cfg.safe_dict()
    assert cfg.safe_dict()["has_api_secret"] is False
    assert cfg.safe_dict()["enable_htf_filter"] is True


def test_htf_filter_env() -> None:
    cfg = load_config(
        environ={"ENABLE_HTF_FILTER": "false"}, load_default_dotenv=False
    )
    assert cfg.enable_htf_filter is False


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
    # Phrase missing: degrade to LIVE_READY instead of live-without-keys.
    degraded = load_config(
        environ={"DRY_RUN": "false", "LIVE_TRADING": "true"},
        load_default_dotenv=False,
    )
    assert degraded.trading_mode == "live_ready"
    assert degraded.may_place_live_orders is False
    with pytest.raises(ConfigError, match="requires BITBANK_API"):
        load_config(
            environ={
                "TRADING_MODE": "live",
                "LIVE_TRADING_CONFIRM": "YES_I_ACCEPT_REAL_MONEY_RISK",
            },
            load_default_dotenv=False,
        )


def test_live_requires_confirm_phrase() -> None:
    cfg = load_config(
        environ={
            "DRY_RUN": "false",
            "LIVE_TRADING": "true",
            "BITBANK_API_KEY": "k",
            "BITBANK_API_SECRET": "s" * 16,
            "LIVE_TRADING_CONFIRM": "YES_I_ACCEPT_REAL_MONEY_RISK",
        },
        load_default_dotenv=False,
    )
    assert cfg.trading_mode == "live"
    assert cfg.may_place_live_orders is True
    assert cfg.live_trading_confirm is True


def test_live_ready_mode() -> None:
    cfg = load_config(
        environ={"TRADING_MODE": "live_ready"},
        load_default_dotenv=False,
    )
    assert cfg.trading_mode == "live_ready"
    assert cfg.dry_run is True
    assert cfg.may_place_live_orders is False
    assert cfg.is_live_ready is True


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
