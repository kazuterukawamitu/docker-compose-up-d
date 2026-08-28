import pytest

from bitbank_bot.config import load_settings
from bitbank_bot.exceptions import ConfigError
from bitbank_bot.logging_setup import redact


def test_load_settings_defaults_to_dry_run(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.delenv("BITBANK_API_KEY", raising=False)
    monkeypatch.delenv("BITBANK_API_SECRET", raising=False)
    monkeypatch.delenv("WIKI_CROSS_RULES", raising=False)
    settings = load_settings(tmp_path / "missing.env")
    assert settings.dry_run is True
    assert settings.pair == "btc_jpy"
    assert settings.wiki_cross_rules is False
    assert settings.no_trade_timeout_seconds == 900


def test_live_without_keys_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("BITBANK_API_KEY", "")
    monkeypatch.setenv("BITBANK_API_SECRET", "")
    with pytest.raises(ConfigError):
        load_settings(tmp_path / "missing.env")


def test_non_btc_pair_rejected(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PAIR", "xrp_jpy")
    monkeypatch.setenv("DRY_RUN", "true")
    with pytest.raises(ConfigError):
        load_settings(tmp_path / "missing.env")


def test_redact_uuid_and_hex() -> None:
    text = "key=aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee secret=" + ("ab" * 32)
    out = redact(text)
    assert "aaaaaaaa-bbbb" not in out
    assert "abababab" not in out
    assert "[REDACTED]" in out
