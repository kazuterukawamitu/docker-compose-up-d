"""Rich terminal dashboard. Falls back to log lines when not a TTY."""

from __future__ import annotations

from decimal import Decimal

from rich.console import Console
from rich.table import Table

from bitbank_bot.config import Settings
from bitbank_bot.models import Position, Signal, Snapshot


class Dashboard:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._console = Console()

    def render(
        self,
        snapshot: Snapshot,
        position: Position,
        signal: Signal,
        jpy: Decimal,
        btc: Decimal,
        note: str,
    ) -> None:
        if not self._settings.dashboard:
            return
        table = Table(title=f"Bitbank {self._settings.pair_display}  dry_run={self._settings.dry_run}")
        table.add_column("field")
        table.add_column("value")
        last = snapshot.ticker.last
        ma = snapshot.ma[-1] if snapshot.ma else Decimal("0")
        table.add_row("last", f"{last} JPY")
        table.add_row("MA", str(ma))
        table.add_row("MA trend", snapshot.ma_trend.value)
        table.add_row("RSI", str(snapshot.rsi[-1] if snapshot.rsi else ""))
        table.add_row("JPY free", str(jpy))
        table.add_row("BTC free", str(btc))
        table.add_row("position BTC", str(position.amount_btc))
        table.add_row("entry", str(position.entry_price or ""))
        table.add_row("signal", f"{signal.side} {signal.reason}")
        table.add_row("note", note)
        self._console.print(table)
