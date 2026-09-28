from __future__ import annotations

import importlib.util
import tarfile
from pathlib import Path

import pytest


def _load():
    path = Path(__file__).resolve().parents[1] / "launch.py"
    spec = importlib.util.spec_from_file_location("bitbank_launch_under_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("launch.py missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_find_project_uses_this_checkout() -> None:
    launch = _load()
    root = Path(__file__).resolve().parents[1]
    assert launch.find_project(root) == root.resolve()


def test_safe_members_drop_parent_and_links(tmp_path: Path) -> None:
    launch = _load()
    archive_path = tmp_path / "src.tar.gz"
    payload = tmp_path / "payload"
    payload.mkdir()
    (payload / "main.py").write_text("print(1)\n", encoding="utf-8")
    outside = tmp_path / "secret"
    outside.write_text("nope", encoding="utf-8")
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(payload / "main.py", arcname="pkg/main.py")
        archive.add(outside, arcname="pkg/../../secret")
        link = tarfile.TarInfo("pkg/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc/passwd"
        archive.addfile(link)
    with tarfile.open(archive_path, "r:gz") as archive:
        names = [member.name for member in launch._safe_members(archive)]
    assert names == ["pkg/main.py"]


def test_launch_check_does_not_need_git(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(Path.cwd())
    launch = _load()
    code = launch.main(["--check", "--no-venv", "--no-download"])
    captured = capsys.readouterr()
    assert code == 0, captured.out + captured.err
    assert "LAUNCH PASS git_login not_required" in captured.out
    assert "DRY_RUN=" in captured.out
    assert "does not enable live orders" in captured.out
    assert "may_place_live_orders" in captured.out


def _bot_archive(tmp_path: Path) -> bytes:
    root = tmp_path / "pkg"
    for rel in (
        "main.py",
        "run.py",
        "requirements.txt",
        ".env.example",
        "src/bitbank_bot/__init__.py",
        "src/bitbank_bot/main.py",
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if rel == "run.py":
            path.write_text('PAIR = "btc_jpy"\ndef main(argv=None):\n    return 0\n', encoding="utf-8")
        else:
            path.write_text("# " + rel + "\n", encoding="utf-8")
    archive_path = tmp_path / "ok.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(root, arcname="pkg")
    return archive_path.read_bytes()


def test_download_uses_second_archive_when_first_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    launch = _load()
    payload = _bot_archive(tmp_path)
    calls = {"n": 0}

    def fake(url: str, limit: int) -> bytes:
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("missing")
        return payload

    monkeypatch.setattr(launch, "_read_url", fake)
    found = launch.download_project(tmp_path / "install")
    assert launch._has_bot(found)
    assert calls["n"] == 2


def test_download_falls_back_to_run_py(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    launch = _load()

    def fake(url: str, limit: int) -> bytes:
        if url.endswith("run.py"):
            return b'PAIR = "btc_jpy"\ndef main(argv=None):\n    return 0\n'
        raise OSError("archive missing")

    monkeypatch.setattr(launch, "_read_url", fake)
    found = launch.download_project(tmp_path / "install")
    assert (found / "run.py").is_file()
    assert not launch._has_bot(found)
    text = (found / "run.py").read_text(encoding="utf-8")
    assert "create_order(" not in text


def test_launch_missing_sources_exits_without_git(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(Path.cwd())
    launch = _load()
    monkeypatch.setattr(launch, "find_project", lambda _script_dir: None)
    code = launch.main(["--check", "--no-venv", "--no-download"])
    captured = capsys.readouterr()
    assert code == 2
    assert "bot files not found" in captured.out
    assert "Git login is not required" in captured.err
    assert "git clone" not in captured.err
    assert "git fetch" not in captured.err
