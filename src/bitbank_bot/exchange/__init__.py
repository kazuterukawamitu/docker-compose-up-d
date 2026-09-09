"""Bitbank-only exchange facades. No other venues are imported."""

from bitbank_bot.exchange.bitbank_adapter import BitbankAdapter

__all__ = ["BitbankAdapter"]
