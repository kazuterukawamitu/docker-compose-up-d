from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch


def _load():
    path = Path(__file__).resolve().parents[1] / "launch_from_git.py"
    spec = importlib.util.spec_from_file_location("bitbank_launch_from_git", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


git_launch = _load()


def test_launch_from_git_compiles() -> None:
    path = Path(__file__).resolve().parents[1] / "launch_from_git.py"
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")
    assert "create_order(" not in source
    assert "/user/spot/order" not in source
    assert "os.execvpe" in source
    assert git_launch.DEFAULT_REPO.startswith("https://github.com/")


def test_parse_override_env_ignores_comments() -> None:
    parsed = git_launch.parse_override_env(
        "# note\nexport LOG_LEVEL=INFO\nBITBANK_PAIR=btc_jpy\n"
    )
    assert parsed == {"LOG_LEVEL": "INFO", "BITBANK_PAIR": "btc_jpy"}


def test_corrections_override_hosted_live_flags() -> None:
    merged = git_launch.apply_corrections(
        {"DRY_RUN": "false", "LIVE_TRADING": "true", "LOG_LEVEL": "DEBUG"}
    )
    assert merged["DRY_RUN"] == "true"
    assert merged["LIVE_TRADING"] == "false"
    assert merged["BITBANK_PAIR"] == "btc_jpy"
    assert merged["LOG_LEVEL"] == "DEBUG"


def test_redact_env_hides_secrets() -> None:
    shown = git_launch.redact_env(
        {
            "DRY_RUN": "true",
            "BITBANK_API_SECRET": "should-not-appear",
            "BITBANK_API_KEY": "also-secret",
        }
    )
    assert shown["DRY_RUN"] == "true"
    assert shown["BITBANK_API_SECRET"] == "[REDACTED]"
    assert shown["BITBANK_API_KEY"] == "[REDACTED]"
    assert "should-not-appear" not in shown.values()


def test_collect_override_files_reads_overrides_dir(tmp_path) -> None:
    overrides = tmp_path / "overrides"
    overrides.mkdir()
    (overrides / "env").write_text("DRY_RUN=true\n", encoding="utf-8")
    (overrides / "extra.env").write_text("LOG_LEVEL=WARNING\n", encoding="utf-8")
    extra = tmp_path / "more.env"
    extra.write_text("ENABLE_WEBSOCKET=false\n", encoding="utf-8")
    files = git_launch.collect_override_files(overrides, [extra])
    merged = git_launch.merge_overrides(files)
    assert merged["DRY_RUN"] == "true"
    assert merged["LOG_LEVEL"] == "WARNING"
    assert merged["ENABLE_WEBSOCKET"] == "false"


def test_parse_args_forwards_bot_flags() -> None:
    ns, forwarded = git_launch.parse_args(
        ["--no-fetch", "--once", "--synthetic", "--skip-lock"]
    )
    assert ns.no_fetch is True
    assert forwarded == ["--once", "--synthetic", "--skip-lock"]


def test_build_command_does_not_inject_once() -> None:
    cmd = git_launch.build_command(sys.executable, Path("/tmp/launch.py"), ["--screen"])
    assert cmd[-1] == "--screen"
    assert "--once" not in cmd


def test_choose_target_prefers_launch_py(tmp_path) -> None:
    (tmp_path / "run.py").write_text("# run\n", encoding="utf-8")
    (tmp_path / "launch.py").write_text("# launch\n", encoding="utf-8")
    assert git_launch.choose_target(tmp_path).name == "launch.py"


def test_refuse_in_place_checkout(capsys) -> None:
    rc = git_launch.launch(["--checkout", "--no-fetch"], exec_target=False)
    assert rc == 2
    err = capsys.readouterr().err
    assert "refusing in-place checkout" in err


def test_launch_from_git_without_exec_applies_corrections(capsys) -> None:
    rc = git_launch.launch(["--no-fetch"], exec_target=False)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Git-hosted bot" in out
    assert "DRY_RUN" in out
    assert "LIVE_TRADING" in out
    assert "should-not-appear" not in out


def test_sync_hosted_tree_clones_when_missing(tmp_path) -> None:
    workdir = tmp_path / "bot"
    calls: list[list[str]] = []

    def fake_git(args: list[str], cwd=None):
        calls.append(args)
        if args[:1] == ["clone"]:
            dest = Path(args[2])
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "run.py").write_text("# bot\n", encoding="utf-8")
            (dest / ".git").mkdir()
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ["fetch", "origin"] or args[:1] == ["checkout"] or args[:1] == [
            "rev-parse"
        ]:
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)

    with patch.object(git_launch, "run_git", side_effect=fake_git):
        git_launch.sync_hosted_tree(
            workdir,
            git_launch.DEFAULT_REPO,
            git_launch.DEFAULT_REF,
            fetch=True,
            checkout=True,
        )
    assert any(c[:1] == ["clone"] for c in calls)
    assert (workdir / "run.py").is_file()


def test_launch_from_git_starts_hosted_tree_once_synthetic(tmp_path) -> None:
    root = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["STATE_PATH"] = str(tmp_path / "state.json")
    env["LOCK_PATH"] = str(tmp_path / "bot.lock")
    env["LOG_DIR"] = str(tmp_path / "logs")
    env["ENABLE_WEBSOCKET"] = "false"
    proc = subprocess.run(
        [
            sys.executable,
            str(root / "launch_from_git.py"),
            "--no-fetch",
            "--once",
            "--synthetic",
            "--skip-lock",
            "--no-screen",
        ],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    combined = proc.stdout + proc.stderr
    assert "Git-hosted bot" in combined
    assert "補正済み DRY_RUN" in combined
    assert "create_order" not in combined
    assert "run_once complete" in combined or "run complete" in combined
    assert "should-not-appear" not in combined
