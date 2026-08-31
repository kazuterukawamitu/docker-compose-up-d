"""Read-only Bitbank execution audit. Never places orders."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.rest_client import RestClient


@dataclass
class AuditReport:
    dry_run: bool
    log_fill_count: int
    log_simulated_count: int
    log_intent_count: int
    exchange_trade_count: int | None
    jpy_free: str | None
    btc_free: str | None
    consistent: bool
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "dry_run": self.dry_run,
            "log_fill_count": self.log_fill_count,
            "log_simulated_count": self.log_simulated_count,
            "log_intent_count": self.log_intent_count,
            "exchange_trade_count": self.exchange_trade_count,
            "jpy_free": self.jpy_free,
            "btc_free": self.btc_free,
            "consistent": self.consistent,
            "notes": list(self.notes),
        }


def scan_log(path: Path) -> tuple[int, int, int]:
    fills = 0
    simulated = 0
    intents = 0
    if not path.exists():
        return fills, simulated, intents
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if " SIMULATED_FILL " in line:
            simulated += 1
        elif " FILL " in line:
            fills += 1
        if " ORDER_INTENT " in line:
            intents += 1
    return fills, simulated, intents


def run_audit(
    cfg: Config,
    client: RestClient,
    log_path: str | Path | None = None,
) -> AuditReport:
    slog("AUDIT", "read-only execution audit start", dry_run=cfg.dry_run)
    path = Path(log_path or Path(cfg.log_dir) / "bot.log")
    fills, simulated, intents = scan_log(path)
    notes: list[str] = []
    trade_count: int | None = None
    jpy_free: str | None = None
    btc_free: str | None = None

    try:
        ticker = client.get_ticker(cfg.pair)
        slog("AUDIT", "public ticker", last=ticker.get("last"))
        notes.append(f"ticker_last={ticker.get('last')}")
    except Exception as exc:
        notes.append(f"ticker_failed={type(exc).__name__}")

    if cfg.has_keys:
        try:
            history = client.get_trade_history(cfg.pair, count=20)
            trades = history.get("trades") if isinstance(history, dict) else None
            if trades is None and isinstance(history, list):
                trades = history
            trade_count = len(trades or [])
            slog("AUDIT", "trade_history", count=trade_count)
        except Exception as exc:
            notes.append(f"trade_history_failed={type(exc).__name__}")
        try:
            jpy_free = str(client.free_amount("jpy"))
            btc_free = str(client.free_amount("btc"))
            slog("AUDIT", "assets", jpy=jpy_free, btc=btc_free)
        except Exception as exc:
            notes.append(f"assets_failed={type(exc).__name__}")
    else:
        notes.append("keys absent; trade_history not queried")

    consistent = True
    if cfg.dry_run and fills > 0:
        consistent = False
        notes.append(
            "DRY_RUN logs contain [FILL] lines; those are not Bitbank executions"
        )
    if cfg.dry_run:
        notes.append("DRY_RUN=true so Bitbank JPY is expected to stay unchanged")
    if not cfg.dry_run and fills > 0 and trade_count == 0:
        consistent = False
        notes.append("live FILL logs exist but trade_history is empty")

    report = AuditReport(
        dry_run=cfg.dry_run,
        log_fill_count=fills,
        log_simulated_count=simulated,
        log_intent_count=intents,
        exchange_trade_count=trade_count,
        jpy_free=jpy_free,
        btc_free=btc_free,
        consistent=consistent,
        notes=notes,
    )
    slog(
        "AUDIT",
        "complete",
        consistent=consistent,
        fills=fills,
        simulated=simulated,
        intents=intents,
        exchange_trades=trade_count,
    )
    return report
