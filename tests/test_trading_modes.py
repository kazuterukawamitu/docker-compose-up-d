from __future__ import annotations

from bitbank_bot.config import LIVE_CONFIRM_PHRASE, MODE_LIVE, MODE_LIVE_READY, load_config


def test_defaults_are_not_live() -> None:
    cfg = load_config(environ={}, load_default_dotenv=False)
    assert cfg.resolved_trading_mode() == "DRY_RUN"
    assert cfg.dry_run is True
    assert cfg.may_place_live_orders is False


def test_live_without_confirm_is_live_ready() -> None:
    cfg = load_config(
        environ={"TRADING_MODE": "LIVE", "BITBANK_API_KEY": "k", "BITBANK_API_SECRET": "s"},
        load_default_dotenv=False,
    )
    assert cfg.resolved_trading_mode() == MODE_LIVE_READY
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
    assert cfg.resolved_trading_mode() == MODE_LIVE
    assert cfg.may_place_live_orders is True
