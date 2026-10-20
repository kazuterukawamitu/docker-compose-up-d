from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_healthcheck():
    path = Path(__file__).resolve().parents[1] / "docker" / "healthcheck.py"
    spec = importlib.util.spec_from_file_location("audit_healthcheck", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_healthcheck_fails_without_report(tmp_path, monkeypatch) -> None:
    module = _load_healthcheck()
    monkeypatch.setenv("AUDIT_REPORT_DIR", str(tmp_path))
    module.REPORT_DIR = tmp_path
    module.REPORT = tmp_path / "report.json"
    module.HEALTH = tmp_path / "health"
    assert module.main() == 1


def test_healthcheck_ok_when_live_no(tmp_path, monkeypatch) -> None:
    module = _load_healthcheck()
    monkeypatch.setenv("AUDIT_REPORT_DIR", str(tmp_path))
    module.REPORT_DIR = tmp_path
    module.REPORT = tmp_path / "report.json"
    module.HEALTH = tmp_path / "health"
    payload = {"LIVE": "NO", "has_secret_values": False, "create_order": False}
    module.REPORT.write_text(json.dumps(payload), encoding="utf-8")
    module.HEALTH.write_text("OK\n", encoding="utf-8")
    assert module.main() == 0


def test_healthcheck_fails_if_live_yes(tmp_path, monkeypatch) -> None:
    module = _load_healthcheck()
    module.REPORT = tmp_path / "report.json"
    module.HEALTH = tmp_path / "health"
    module.REPORT.write_text(
        json.dumps({"LIVE": "YES", "has_secret_values": False, "create_order": False}),
        encoding="utf-8",
    )
    module.HEALTH.write_text("OK\n", encoding="utf-8")
    assert module.main() == 1
