from __future__ import annotations

import logging
from dataclasses import dataclass, field

from bitbank_bot.config import Settings
from bitbank_bot.exceptions import AuthError, ExchangeError
from bitbank_bot.exchange.bitbank_rest import BitbankRest
from bitbank_bot.exchange.bitbank_ws import BitbankPublicWS
from bitbank_bot.market.cache import MarketCache

log = logging.getLogger(__name__)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


@dataclass
class PreflightReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.checks.append(CheckResult(name, ok, detail))
        level = logging.INFO if ok else logging.ERROR
        log.log(level, "preflight %s: %s (%s)", "OK" if ok else "FAIL", name, detail)


async def run_preflight(settings: Settings, include_private: bool = False) -> PreflightReport:
    report = PreflightReport()
    cache = MarketCache()
    async with BitbankRest(settings) as rest:
        try:
            ticker = await rest.fetch_ticker(settings.pair)
            cache.upsert_ticker(ticker, source="rest")
            report.add("public_ticker", True, f"last={ticker.last} ts={ticker.timestamp_ms}")
        except Exception as exc:
            log.exception("ticker failed")
            report.add("public_ticker", False, str(exc))
        try:
            mode = await rest.fetch_circuit_break(settings.pair)
            report.add("circuit_break_info", True, f"mode={mode}")
        except Exception as exc:
            log.exception("circuit_break_info failed")
            report.add("circuit_break_info", False, str(exc))
        try:
            candles = await rest.fetch_candles(settings.pair, settings.candle_type, min_bars=30)
            report.add("candles", len(candles) >= 10, f"n={len(candles)} type={settings.candle_type}")
        except Exception as exc:
            log.exception("candles failed")
            report.add("candles", False, str(exc))
        if include_private and settings.api_key and settings.api_secret:
            try:
                assets = await rest.fetch_assets()
                jpy = assets.get("jpy")
                btc = assets.get("btc")
                report.add(
                    "private_assets",
                    True,
                    f"jpy_free={jpy.free if jpy else 'n/a'} btc_free={btc.free if btc else 'n/a'}",
                )
            except AuthError as exc:
                report.add("private_assets", False, f"auth failed: {exc}")
            except ExchangeError as exc:
                report.add("private_assets", False, str(exc))
        elif include_private:
            report.add("private_assets", False, "keys not configured")
        else:
            report.add("private_assets", True, "skipped (no live keys requested)")

    ws = BitbankPublicWS(settings, cache)
    try:
        import asyncio

        task = asyncio.create_task(ws.run())
        for _ in range(50):
            await asyncio.sleep(0.2)
            if cache.ticker is not None and cache.ws_connected:
                break
        ws.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        ok = cache.ticker is not None
        report.add("websocket_ticker", ok, f"last={cache.ticker.last if cache.ticker else 'n/a'}")
    except Exception as exc:
        log.exception("websocket preflight failed")
        report.add("websocket_ticker", False, str(exc))
    return report
