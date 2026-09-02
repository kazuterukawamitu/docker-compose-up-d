from __future__ import annotations

from bitbank_bot.logging_setup import redact, slog


def test_has_api_secret_not_redacted_in_key_name() -> None:
    line = redact('{"has_api_secret": false, "dry_run": true}')
    assert "has_api_secret" in line
    assert "[REDACTED]" not in line


def test_hmac_hex_redacted() -> None:
    sig = "a" * 64
    assert "[REDACTED]" in redact(f"ACCESS-SIGNATURE={sig}")


def test_slog_safe_dict_keys(caplog) -> None:
    with caplog.at_level("INFO", logger="bitbank_bot"):
        slog("BOOT", "starting", has_api_secret=False, dry_run=True)
    text = caplog.text
    assert "has_api_secret" in text
    assert "false" in text
