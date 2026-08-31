import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_start_sh_guards_repo_root() -> None:
    text = (ROOT / "start.sh").read_text(encoding="utf-8")
    assert "src/bitbank_bot/__init__.py" in text
    assert "requirements.txt" in text
    assert ".env.example" in text
    assert "python3.12" in text
    assert "No module named bitbank_bot" not in text or "venv" in text


def test_start_sh_syntax() -> None:
    subprocess.run(["bash", "-n", str(ROOT / "start.sh")], check=True)


def test_install_vps_syntax() -> None:
    subprocess.run(["bash", "-n", str(ROOT / "scripts/install-vps.sh")], check=True)


def test_systemd_restarts_always() -> None:
    unit = (ROOT / "deploy/bitbank-bot.service").read_text(encoding="utf-8")
    assert "Restart=always" in unit
    assert "WorkingDirectory=/opt/bitbank-bot" in unit
    assert "/Users/" not in unit
