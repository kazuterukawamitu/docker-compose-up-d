from decimal import Decimal
from pathlib import Path

import pytest

from bitbank_bot.config import load_settings
from bitbank_bot.exceptions import ConfigError


def test_dry_run_defaults_true(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.delenv("BITBANK_API_KEY", raising=False)
    monkeypatch.delenv("BITBANK_API_SECRET", raising=False)
    monkeypatch.chdir(tmp_path)
    settings = load_settings(env_file=None)
    assert settings.dry_run is True
    assert settings.pair == "btc_jpy"
    assert settings.min_order_btc == Decimal("0.0001")


def test_rejects_wrong_pair(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PAIR", "eth_jpy")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError):
        load_settings(env_file=None)


def test_live_requires_keys(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("BITBANK_API_KEY", "")
    monkeypatch.setenv("BITBANK_API_SECRET", "")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError):
        load_settings(env_file=None)
