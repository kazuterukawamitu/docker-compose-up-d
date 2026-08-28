from __future__ import annotations

import logging
import os
import sys
import time
from decimal import Decimal

from bitbank_bot.config import Settings
from bitbank_bot.models import BotStats, Position, Snapshot

log = logging.getLogger(__name__)

_DASHBOARD_DISABLED = False


def render_status(settings: Settings, snapshot: Snapshot, stats: BotStats, position: Position) -> None:
    last = snapshot.ticker.last
    uptime = max(0, int(time.time() * 1000) - stats.started_ms) // 1000
    pnl = position.unrealized_pnl(last)
    line = (
        f"{settings.display_pair} last={last} dry_run={settings.dry_run} "
        f"pos={position.amount}@{position.entry_price} uPnL={pnl} "
        f"realized={stats.realized_pnl} wr={_pct(stats.win_rate)} "
        f"signal={stats.last_signal.action if stats.last_signal else 'n/a'} "
        f"ws={snapshot.ws_ok} uptime_s={uptime}"
    )
    if not settings.dashboard or not sys.stdout.isatty() or os.environ.get("BITBANK_BOT_NO_RICH"):
        log.info(line)
        return
    try:
        from rich.console import Console
        from rich.table import Table

        table = Table(title="bitbank BTC/JPY")
        table.add_column("field")
        table.add_column("value")
        rows = {
            "pair": settings.display_pair,
            "last": str(last),
            "dry_run": str(settings.dry_run),
            "position": f"{position.amount} @ {position.entry_price}",
            "unrealized_pnl": str(pnl),
            "realized_pnl": str(stats.realized_pnl),
            "daily_pnl": str(stats.daily_realized_pnl),
            "win_rate": _pct(stats.win_rate),
            "signal": f"{stats.last_signal.action} {stats.last_signal.rule_id}" if stats.last_signal else "n/a",
            "reason": stats.last_signal.reason if stats.last_signal else "",
            "block": stats.last_block_reason,
            "ws": str(snapshot.ws_ok),
            "circuit": snapshot.circuit_mode,
            "watchdog": stats.last_watch_status or "n/a",
            "uptime_s": str(uptime),
        }
        for key, value in rows.items():
            table.add_row(key, value)
        Console().print(table)
    except Exception:
        global _DASHBOARD_DISABLED
        if not _DASHBOARD_DISABLED:
            log.exception("dashboard render failed; falling back to logs")
            _DASHBOARD_DISABLED = True
        log.info(line)


def _pct(value: Decimal) -> str:
    return f"{(value * 100):.1f}%"
