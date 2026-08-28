class BotError(Exception):
    """Base error for the trading bot."""


class ExchangeError(BotError):
    def __init__(self, message: str, code: int | None = None, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class AuthError(ExchangeError):
    pass


class RateLimitError(ExchangeError):
    pass


class StaleDataError(BotError):
    pass


class RiskBlocked(BotError):
    """Order was refused by risk controls. Not an exchange failure."""


class ConfigError(BotError):
    pass
