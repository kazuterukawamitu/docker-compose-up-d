from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAC_GO = (
    "cd ~/docker-compose-up-d && git fetch origin cursor/bitbank-closed-loop-1114 && "
    "git checkout -B cursor/bitbank-closed-loop-1114 origin/cursor/bitbank-closed-loop-1114 && "
    "bash ./start.sh --go"
)


def _env(tmp_path: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["STATE_PATH"] = str(tmp_path / "state.json")
    env["LOCK_PATH"] = str(tmp_path / "bot.lock")
    env["LOG_DIR"] = str(tmp_path / "logs")
    env["DRY_RUN"] = "true"
    env["LIVE_TRADING"] = "false"
    env["ENABLE_WEBSOCKET"] = "false"
    return env


def _run(args: list[str], tmp_path: Path, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd or ROOT),
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_closed_loop_review(tmp_path) -> None:
    proc = _run([sys.executable, str(ROOT / "closed_loop.py"), "--review"], tmp_path)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "LAUNCH_OK" in proc.stdout
    assert MAC_GO in proc.stdout
    assert "Do NOT run" in proc.stdout
    assert "BadDsn" in proc.stdout
    assert "bash ./start.sh --go" in proc.stdout


def test_start_sh_help_from_other_cwd(tmp_path) -> None:
    proc = _run(["bash", str(ROOT / "start.sh"), "--help"], tmp_path, cwd=tmp_path)
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "LAUNCH_OK" in out
    assert MAC_GO in out
    assert str(ROOT) in out
    assert "home finder" in out


def test_closed_loop_verify_no_public(tmp_path) -> None:
    proc = _run(
        [sys.executable, str(ROOT / "closed_loop.py"), "--verify", "--no-public"],
        tmp_path,
    )
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "LAUNCH_OK" in out
    assert "run_once complete" in out
    assert "may_place_live_orders" in out


def test_src_main_py_without_pythonpath(tmp_path) -> None:
    proc = _run(
        [sys.executable, str(ROOT / "src" / "bitbank_bot" / "main.py"), "--check-config"],
        tmp_path,
    )
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "LAUNCH_OK" in out
    assert "No module named 'bitbank_bot'" not in out


def test_dash_m_bitbank_bot_from_repo_root(tmp_path) -> None:
    proc = _run([sys.executable, "-m", "bitbank_bot", "--check-config"], tmp_path)
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "LAUNCH_OK" in out
    assert "No module named 'bitbank_bot'" not in out


def test_root_main_py_check_config(tmp_path) -> None:
    proc = _run([sys.executable, str(ROOT / "main.py"), "--check-config"], tmp_path)
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "LAUNCH_OK" in out


def test_closed_loop_go_from_other_cwd(tmp_path) -> None:
    proc = _run(
        [sys.executable, str(ROOT / "closed_loop.py"), "--go"],
        tmp_path,
        cwd=tmp_path,
    )
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "LAUNCH_OK" in out
    assert "run_once complete" in out
    assert "No module named 'bitbank_bot'" not in out


def test_closed_loop_go_from_fake_home_ignores_home_main_py(tmp_path) -> None:
    home = tmp_path / "Users" / "kazuterukawamitsu"
    home.mkdir(parents=True)
    (home / "main.py").write_text(
        "raise SystemExit('SENTRY_MAIN_SHOULD_NOT_RUN')\n",
        encoding="utf-8",
    )
    (home / "closed_loop.py").write_text(
        "raise SystemExit('HOME_CLOSED_LOOP_SHOULD_NOT_RUN')\n",
        encoding="utf-8",
    )
    proc = _run(
        [sys.executable, str(ROOT / "closed_loop.py"), "--go"],
        tmp_path,
        cwd=home,
    )
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "SENTRY_MAIN_SHOULD_NOT_RUN" not in out
    assert "HOME_CLOSED_LOOP_SHOULD_NOT_RUN" not in out
    assert "BadDsn" not in out
    assert "LAUNCH_OK" in out
    assert "run_once complete" in out


def test_repo_main_py_from_fake_home_ignores_sentry_main(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "main.py").write_text(
        "raise SystemExit('SENTRY_MAIN_SHOULD_NOT_RUN')\n",
        encoding="utf-8",
    )
    proc = _run(
        [sys.executable, str(ROOT / "main.py"), "--go"],
        tmp_path,
        cwd=home,
    )
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "SENTRY_MAIN_SHOULD_NOT_RUN" not in out
    assert "LAUNCH_OK" in out
    assert "run_once complete" in out


def test_relative_closed_loop_from_home_is_missing(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    proc = _run([sys.executable, "closed_loop.py", "--go"], tmp_path, cwd=home)
    out = proc.stderr + proc.stdout
    assert proc.returncode != 0
    assert "can't open file" in out or "No such file" in out


def test_closed_loop_missing_source_prints_mac_go(tmp_path) -> None:
    isolated = tmp_path / "only_launcher"
    isolated.mkdir()
    (isolated / "closed_loop.py").write_text(
        (ROOT / "closed_loop.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(isolated / "closed_loop.py"), "--go"],
        cwd=str(tmp_path),
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        timeout=30,
    )
    out = proc.stderr + proc.stdout
    assert proc.returncode == 2, out
    assert "LAUNCH_FAIL" in out
    assert MAC_GO in out


def test_closed_loop_go_prints_launch_ok(tmp_path) -> None:
    proc = _run([sys.executable, str(ROOT / "closed_loop.py"), "--go"], tmp_path)
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "LAUNCH_OK" in proc.stdout
    assert "run_once complete" in out


def test_closed_loop_no_args_is_go(tmp_path) -> None:
    proc = _run([sys.executable, str(ROOT / "closed_loop.py")], tmp_path)
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "LAUNCH_OK" in out
    assert "run_once complete" in out


def test_root_main_py_no_args_is_go(tmp_path) -> None:
    proc = _run([sys.executable, str(ROOT / "main.py")], tmp_path)
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "LAUNCH_OK" in out
    assert "run_once complete" in out


def test_src_main_py_no_args_is_go(tmp_path) -> None:
    proc = _run(
        [sys.executable, str(ROOT / "src" / "bitbank_bot" / "main.py")],
        tmp_path,
    )
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "LAUNCH_OK" in out
    assert "run_once complete" in out


def test_dash_m_bitbank_bot_no_args_is_go(tmp_path) -> None:
    proc = _run([sys.executable, "-m", "bitbank_bot"], tmp_path)
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "LAUNCH_OK" in out
    assert "run_once complete" in out


def _start_sh(tmp_path: Path, cwd: Path, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = _env(tmp_path)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(ROOT / "start.sh"), "--go"],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_start_sh_go(tmp_path) -> None:
    proc = _start_sh(tmp_path, ROOT)
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "LAUNCH_OK" in out
    assert "run_once complete" in out


def test_start_sh_go_from_fake_home(tmp_path) -> None:
    home = tmp_path / "Users" / "kazuterukawamitsu"
    home.mkdir(parents=True)
    (home / "main.py").write_text(
        "raise SystemExit('SENTRY_MAIN_SHOULD_NOT_RUN')\n",
        encoding="utf-8",
    )
    proc = _start_sh(tmp_path, home)
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "SENTRY_MAIN_SHOULD_NOT_RUN" not in out
    assert "LAUNCH_OK" in out
    assert "run_once complete" in out


def test_readme_leads_with_mac_go() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert MAC_GO in text
    assert "BadDsn" in text
    assert "/path/to/" in text
    assert "closed-loop-launcher-563e" in text


def test_mac_go_sh_from_fake_home(tmp_path) -> None:
    home = tmp_path / "Users" / "kazuterukawamitsu"
    home.mkdir(parents=True)
    (home / "main.py").write_text(
        "raise SystemExit('SENTRY_MAIN_SHOULD_NOT_RUN')\n",
        encoding="utf-8",
    )
    env = _env(tmp_path)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    proc = subprocess.run(
        ["bash", str(ROOT / "scripts" / "mac_go.sh")],
        cwd=str(home),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = proc.stderr + proc.stdout
    assert proc.returncode == 0, out
    assert "SENTRY_MAIN_SHOULD_NOT_RUN" not in out
    assert "LAUNCH_OK" in out
    assert "run_once complete" in out
    text = (ROOT / "scripts" / "mac_go.sh").read_text(encoding="utf-8")
    assert MAC_GO in text
    assert 'BRANCH="cursor/bitbank-closed-loop-1114"' in text
