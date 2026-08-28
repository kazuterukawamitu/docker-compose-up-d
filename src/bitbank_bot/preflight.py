"""Preflight: pair, min size, public API, optional private balance (never places orders)."""

from __future__ import annotations

import logging
from decimal import Decimal

from bitbank_bot.config import Settings
from bitbank_bot.exceptions import ConfigError, ExchangeError
from bitbank_bot.exchange.rest import BitbankRest

log = logging.getLogger("bitbank_bot.preflight")


async def run_preflight(settings: Settings, rest: BitbankRest) -> dict[str, str]:
    if settings.pair != "btc_jpy":
        raise ConfigError("pair must be btc_jpy")
    if settings.min_order_btc != Decimal("0.0001"):
        raise ConfigError("Bitbank BTC/JPY min size must stay 0.0001")

    ticker = await rest.get_ticker()
    depth = await rest.get_depth()
    candles = await rest.get_candles()
    circuit = await rest.get_circuit_break()
    report = {
        "pair": settings.pair_display,
        "dry_run": str(settings.dry_run),
        "last": str(ticker.last),
        "bid": str(ticker.bid),
        "ask": str(ticker.ask),
        "bids": str(len(depth.bids)),
        "asks": str(len(depth.asks)),
        "candles": str(len(candles)),
        "circuit_mode": str(circuit.get("mode")),
    }
    if not settings.dry_run:
        jpy, btc = await rest.get_balances()
        report["jpy_free"] = str(jpy.free)
        report["btc_free"] = str(btc.free)
        if jpy.free <= 0 and btc.free <= 0:
            raise ExchangeError("both JPY and BTC free balances are zero")
    log.info("preflight ok %s", report)
    return report
