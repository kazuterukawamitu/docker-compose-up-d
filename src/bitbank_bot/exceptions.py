"""Domain exceptions. Live-order paths never retry blindly after a timeout."""


class BotError(Exception):
    """Base error for the trading bot."""


class ConfigError(BotError):
    """Invalid or unsafe configuration."""


class ExchangeError(BotError):
    """Bitbank REST/WebSocket failure."""


class AuthError(ExchangeError):
    """Private API authentication failed."""


class RateLimitError(ExchangeError):
    """HTTP 429 from Bitbank."""


class CircuitBreakerError(ExchangeError):
    """Spot market is in circuit-breaker / itayose mode."""


class InsufficientFundsError(BotError):
    """Balance too small for the minimum order."""


class OrderUncertainError(BotError):
    """POST /order timed out; fill state is unknown. Do not resubmit."""


class LockError(BotError):
    """Another bot instance already holds the lock file."""
