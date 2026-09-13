from __future__ import annotations

import json
from pathlib import Path

import closed_loop


def test_closed_loop_verify_without_public(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(closed_loop, "ROOT", tmp_path)
    (tmp_path / "logs").mkdir()
    (tmp_path / "data").mkdir()
    rc = closed_loop.verify(public=False)
    assert rc == 0


def test_closed_loop_review_json() -> None:
    assert closed_loop.main(["--review"]) == 0
    assert "closed_loop.py" in closed_loop.PROGRAM_REVIEW["added"]
    assert closed_loop.PROGRAM_REVIEW["removed"] == []


def test_closed_loop_source_is_launchable() -> None:
    path = Path(__file__).resolve().parents[1] / "closed_loop.py"
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")
    assert "if __name__ == \"__main__\"" in source
    assert "may_place_live_orders" in source
