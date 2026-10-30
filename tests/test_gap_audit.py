from __future__ import annotations

import json
from pathlib import Path

from bitbank_bot.gap_audit import run_gap_audit


def test_gap_audit_records_v31_oos_and_keeps_live_no() -> None:
    report = run_gap_audit()
    by_id = {row.id: row for row in report.criteria}
    assert report.live == "NO"
    assert report.has_secret_values is False
    assert by_id["live_default"].status == "PASS"
    assert by_id["create_order_gate"].status == "PASS"
    assert by_id["v31_plugin"].status == "PASS"
    assert by_id["oos_plugin"].status == "PASS"
    assert by_id["oos_no_create_order"].status == "PASS"
    assert by_id["shadow_timer_no_fake_yes"].status == "PASS"
    assert by_id["guard_timer_no_fake_yes"].status == "PASS"
    assert by_id["dual_run_wired"].status == "PASS"
    assert by_id["docker_audit_files"].status == "PASS"
    assert by_id["docker_no_secrets"].status == "PASS"
    assert by_id["compose_dry_run_pytest"].status == "PASS"
    assert by_id["quality_pipeline"].status == "PASS"
    assert by_id["no_secrets_in_report"].status == "PASS"
    blob = json.dumps(report.as_dict())
    assert "BITBANK_API_SECRET=" not in blob


def test_docker_compose_has_healthcheck_no_env_file() -> None:
    root = Path(__file__).resolve().parents[1]
    compose = (root / "docker" / "compose.audit.yml").read_text(encoding="utf-8")
    dry = (root / "docker" / "compose.dry-run.yml").read_text(encoding="utf-8")
    dockerfile = (root / "docker" / "Dockerfile.audit").read_text(encoding="utf-8")
    ignore = (root / ".dockerignore").read_text(encoding="utf-8")
    assert "healthcheck:" in compose
    assert "docker/healthcheck.py" in compose
    assert "env_file:" not in compose
    assert "env_file:" not in dry
    assert "COPY .env" not in dockerfile
    assert not any(line.strip().startswith("- .env") for line in compose.splitlines())
    assert "DRY_RUN=true" in dockerfile
    assert "LIVE_TRADING=false" in dockerfile
    assert ".env" in ignore
    agent = (root / "docker" / "audit_agent.py").read_text(encoding="utf-8")
    assert "create_order(" not in agent
    assert "private_post(" not in agent
