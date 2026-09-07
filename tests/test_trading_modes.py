from __future__ import annotations

from bitbank_bot.config import LIVE_CONFIRM_PHRASE, load_config


def test_defaults_are_not_live() -> None:
    cfg = load_config(environ={}, load_default_dotenv=False)
    assert cfg.trading_mode == "DRY_RUN"
    assert cfg.dry_run is True
    assert cfg.live_trading is False
    assert cfg.live_trading_confirm == ""
    assert cfg.live_trading_confirmed is False
    assert cfg.may_place_live_orders is False
    print(
        "TRADING_MODE",
        cfg.trading_mode,
        "LIVE_READY",
        cfg.is_live_ready,
        "LIVE",
        cfg.is_live,
        "LIVE_TRADING_CONFIRM_SET",
        cfg.live_trading_confirmed,
    )


def test_signal_only_maps_to_live_ready() -> None:
    cfg = load_config(environ={"TRADING_MODE": "SIGNAL_ONLY"}, load_default_dotenv=False)
    assert cfg.trading_mode == "LIVE_READY"
    assert cfg.may_place_live_orders is False


def test_live_without_confirm_is_live_ready() -> None:
    cfg = load_config(
        environ={"TRADING_MODE": "LIVE", "BITBANK_API_KEY": "k", "BITBANK_API_SECRET": "s"},
        load_default_dotenv=False,
    )
    assert cfg.trading_mode == "LIVE_READY"
    assert cfg.may_place_live_orders is False


def test_live_dual_authorized() -> None:
    cfg = load_config(
        environ={
            "TRADING_MODE": "LIVE",
            "LIVE_TRADING_CONFIRM": LIVE_CONFIRM_PHRASE,
            "BITBANK_API_KEY": "k",
            "BITBANK_API_SECRET": "s",
        },
        load_default_dotenv=False,
    )
    assert cfg.trading_mode == "LIVE"
    assert cfg.may_place_live_orders is True
