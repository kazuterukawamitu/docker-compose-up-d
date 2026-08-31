from pathlib import Path

from bitbank_bot.diagnostics import run_diagnostics
from bitbank_bot.main import main

from helpers import cfg


class NoOrderClient:
    def __init__(self) -> None:
        self.create_calls = 0

    def get_ticker(self, pair: str) -> dict[str, str]:
        return {"last": "10000000"}

    def get_spot_status(self, pair: str) -> dict[str, str]:
        return {"pair": pair, "status": "NORMAL", "min_amount": "0.0001"}

    def get_assets(self) -> dict[str, list]:
        return {"assets": []}

    def create_order(self, **kwargs):  # pragma: no cover - must not run
        self.create_calls += 1
        raise AssertionError("diagnostics must not place orders")


def test_diagnostics_never_places_order(tmp_path: Path) -> None:
    client = NoOrderClient()
    c = cfg(
        dry_run=True,
        live_trading=False,
        log_dir=str(tmp_path / "logs"),
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        kill_switch_path=str(tmp_path / "KILL"),
    )
    report = run_diagnostics(c, client, require_public=True)
    assert report["places_orders"] is False
    assert client.create_calls == 0
    assert report["ok"] is True


def test_diagnostics_cli(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("LIVE_TRADING", "false")
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("LOCK_PATH", str(tmp_path / "bot.lock"))
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))
    assert main(["--diagnostics"]) == 0
