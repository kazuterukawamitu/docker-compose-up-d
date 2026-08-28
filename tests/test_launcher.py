import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_run():
    spec = importlib.util.spec_from_file_location("bitbank_run", ROOT / "run.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_py_compiles() -> None:
    source = (ROOT / "run.py").read_text(encoding="utf-8")
    compile(source, str(ROOT / "run.py"), "exec")


def test_start_sh_uses_script_directory_and_pip_module() -> None:
    text = (ROOT / "start.sh").read_text(encoding="utf-8")
    assert 'ROOT="$(cd "$(dirname "$0")" && pwd)"' in text
    assert "-m pip" in text
    assert "run.py" in text
    assert ".env.example" in text
    assert 'exec "$VENV_PY" "$ROOT/run.py" "$@"' in text
    assert "chmod: start.sh: No such file or directory" in text
    assert "cursor/bitbank-btc-jpy-bot-09cf" in text
    assert "ensurepip" in text or "venv を作れませんでした" in text


def test_start_sh_is_tracked_executable() -> None:
    out = subprocess.check_output(["git", "ls-files", "-s", "start.sh"], cwd=ROOT, text=True)
    assert out.startswith("100755"), out


def test_readme_tells_bash_start_not_chmod_from_home() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "bash ./start.sh --preflight" in text
    assert "bash ./start.sh" in text
    assert "chmod: start.sh: No such file or directory" in text
    assert "git clone -b cursor/bitbank-btc-jpy-bot-09cf" in text
    assert "cd ~\nchmod +x start.sh" not in text


def test_run_py_rejects_missing_package(tmp_path, monkeypatch) -> None:
    module = _load_run()
    monkeypatch.setattr(module, "PACKAGE", tmp_path / "missing.py")
    try:
        module.require_repo()
        raise AssertionError("expected SystemExit")
    except SystemExit as exc:
        assert exc.code == 2


def test_start_sh_bash_syntax() -> None:
    result = subprocess.run(["bash", "-n", str(ROOT / "start.sh")], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_run_py_help_works_from_another_directory(tmp_path) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "run.py"), "--help"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "preflight" in result.stdout
