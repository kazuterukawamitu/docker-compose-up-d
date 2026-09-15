from __future__ import annotations

from pathlib import Path

from bitbank_bot.code_audit import (
    SRC_CREATE_ORDER_ALLOWED,
    analyze_python,
    completion_checks,
    dump_paths,
    write_ast_reports,
    write_dump,
)


def test_src_create_order_calls_are_only_order_path() -> None:
    root = Path(__file__).resolve().parents[1]
    report = analyze_python(root)
    assert report["parse_errors"] == []
    assert report["unexpected_src_create_order_calls"] == []
    files = {row["file"] for row in report["src_create_order_calls"]}
    assert files <= SRC_CREATE_ORDER_ALLOWED
    assert "src/bitbank_bot/orders.py" in files
    assert report["other_exchanges_in_src"] == []


def test_completion_percent_excludes_live_post() -> None:
    root = Path(__file__).resolve().parents[1]
    spec = completion_checks(root)
    assert spec["live_post"] == "NOT_TESTED"
    assert spec["passed"] == spec["scored"]
    assert spec["completion_percent"] == 100
    skipped = [row for row in spec["checks"] if row["skip"]]
    assert skipped and skipped[0]["id"] == "11"


def test_source_dump_excludes_env_and_is_not_executable(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    dest = tmp_path / "trading_bot_all_source.txt"
    write_dump(root, dest)
    text = dest.read_text(encoding="utf-8")
    assert "ANALYSIS DUMP ONLY" in text
    assert "NOT AN EXECUTABLE PROGRAM" in text
    assert "# SOURCE: src/bitbank_bot/engine.py" in text
    assert "# SOURCE: start.sh" in text
    assert ".env\n" not in text
    for path in dump_paths(root):
        assert path.name != ".env"
    assert "BITBANK_API_SECRET=" not in text or "[REDACTED]" in text


def test_write_ast_reports(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    rc = write_ast_reports(root, tmp_path)
    assert rc == 0
    assert (tmp_path / "ast_report.json").is_file()
    assert (tmp_path / "dependency_graph.json").is_file()
    assert (tmp_path / "FILE_INVENTORY.md").is_file()
    assert (tmp_path / "completion_spec.json").is_file()
    inventory = (tmp_path / "FILE_INVENTORY.md").read_text(encoding="utf-8")
    assert "leftover_wiki_html" in inventory
    assert "src/bitbank_bot/api_client.py" in inventory
    assert "trading_bot/" not in inventory or "did not invent" in inventory
