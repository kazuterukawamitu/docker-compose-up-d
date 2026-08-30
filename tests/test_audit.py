from pathlib import Path

from bitbank_bot.audit import scan_log


def test_scan_log_counts_fill_vs_simulated(tmp_path: Path) -> None:
    log = tmp_path / "bot.log"
    log.write_text(
        "\n".join(
            [
                "2026-01-01T00:00:00 INFO ORDER_INTENT dry-run; create_order not called",
                "2026-01-01T00:00:01 INFO SIMULATED_FILL paper only; Bitbank JPY unchanged",
                "2026-01-01T00:00:02 INFO FILL ledger executed_amount=0.01",
                "2026-01-01T00:00:03 INFO SIGNAL BUY1",
            ]
        ),
        encoding="utf-8",
    )
    fills, simulated, intents = scan_log(log)
    assert fills == 1
    assert simulated == 1
    assert intents == 1


def test_scan_missing_log() -> None:
    assert scan_log(Path("/tmp/does-not-exist-bitbank-audit.log")) == (0, 0, 0)
