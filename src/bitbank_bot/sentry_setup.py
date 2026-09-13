"""Optional Sentry hook. Secrets are stripped before send. sentry-sdk is optional."""

from __future__ import annotations

from typing import Any

from bitbank_bot.logging_setup import slog


def _strip_secrets(event: dict[str, Any], _hint: dict[str, Any] | None = None) -> dict[str, Any]:
    blocked = ("api_key", "api_secret", "secret", "signature", "authorization", "token")

    def walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {
                key: "[REDACTED]" if any(b in str(key).lower() for b in blocked) else walk(value)
                for key, value in obj.items()
            }
        if isinstance(obj, list):
            return [walk(item) for item in obj]
        if isinstance(obj, str) and len(obj) == 64 and all(c in "0123456789abcdefABCDEF" for c in obj):
            return "[REDACTED]"
        return obj

    return walk(event)


def init_sentry(dsn: str) -> None:
    if not dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        slog("BOOT", "sentry-sdk not installed; continuing without Sentry")
        return
    sentry_sdk.init(
        dsn=dsn,
        traces_sample_rate=0.0,
        send_default_pii=False,
        before_send=_strip_secrets,
    )
    sentry_sdk.set_tag("exchange", "bitbank")
    sentry_sdk.set_tag("pair", "btc_jpy")
    slog("BOOT", "sentry initialized")
