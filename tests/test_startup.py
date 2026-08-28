import json
from pathlib import Path

import pytest

from bitbank_bot.config import ConfigError, load_config
from bitbank_bot.main import main


def test_live_and_dry_run_cannot_both_be_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("LIVE_TRADING", "true")
    with pytest.raises(ConfigError):
        load_config(load_default_dotenv=False, environ=__import__("os").environ)


def test_check_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("LIVE_TRADING", "false")
    monkeypatch.setenv("LOCK_PATH", str(tmp_path / "bot.lock"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))
    assert main(["--check-config"]) == 0


def test_once_synthetic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("LIVE_TRADING", "false")
    monkeypatch.setenv("ENABLE_WEBSOCKET", "false")
    monkeypatch.setenv("LOCK_PATH", str(tmp_path / "bot.lock"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))
    rc = main(["--once", "--synthetic", "--skip-lock"])
    assert rc == 0
    # synthetic dry-run may write state; never a live order file
    if (tmp_path / "state.json").exists():
        payload = json.loads((tmp_path / "state.json").read_text())
        assert "position" in payload


def test_once_dry_run_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("LIVE_TRADING", "true")
    monkeypatch.setenv("BITBANK_API_KEY", "paper-key")
    monkeypatch.setenv("BITBANK_API_SECRET", "paper-secret")
    monkeypatch.setenv("ENABLE_WEBSOCKET", "false")
    monkeypatch.setenv("LOCK_PATH", str(tmp_path / "bot.lock"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))
    rc = main(["--once", "--synthetic", "--skip-lock", "--dry-run"])
    assert rc == 0


def test_backtest_synthetic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("LIVE_TRADING", "false")
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    assert main(["--backtest", "--skip-lock"]) == 0
