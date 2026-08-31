from __future__ import annotations

import py_compile
from pathlib import Path

from bitbank_bot.config import load_config
from bitbank_bot.main import main


def test_compileall_src() -> None:
    root = Path(__file__).resolve().parents[1]
    for path in (root / "src").rglob("*.py"):
        py_compile.compile(str(path), doraise=True)
    py_compile.compile(str(root / "main.py"), doraise=True)


def test_check_config_exit_zero() -> None:
    assert main(["--check-config"]) == 0


def test_synthetic_once_cli(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("LOCK_PATH", str(tmp_path / "bot.lock"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("LIVE_TRADING", "false")
    monkeypatch.setenv("ENABLE_WEBSOCKET", "false")
    rc = main(["--once", "--synthetic", "--dry-run", "--skip-lock"])
    assert rc == 0


def test_load_config_default_pair() -> None:
    cfg = load_config(environ={"DRY_RUN": "true"}, load_default_dotenv=False)
    assert cfg.pair == "btc_jpy"
