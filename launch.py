#!/usr/bin/env python3
"""Launch the Bitbank BTC/JPY bot (the target program).

This file only starts the bot. It does not place orders, enable live trading,
or pass --once unless you pass that flag yourself.

    python3 launch.py
    python3 launch.py --screen
    python3 launch.py --once --synthetic --skip-lock

Prefers the full package via main.py when httpx is installed. Otherwise starts
the stdlib DRY_RUN screen in run.py. Default is a continuous loop.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAIN_PY = ROOT / "main.py"
RUN_PY = ROOT / "run.py"


def ensure_env(root: Path = ROOT) -> Path | None:
    """Create .env from the example so DRY_RUN=true is the default."""
    dest = root / ".env"
    example = root / ".env.example"
    if dest.is_file() or not example.is_file():
        return None
    dest.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


def package_ready(root: Path = ROOT) -> bool:
    if not (root / "src" / "bitbank_bot" / "__init__.py").is_file():
        return False
    if not (root / "main.py").is_file():
        return False
    try:
        import httpx  # noqa: F401
    except ImportError:
        return False
    return True


def choose_target(root: Path = ROOT) -> Path:
    if package_ready(root):
        return root / "main.py"
    if (root / "run.py").is_file():
        return root / "run.py"
    raise FileNotFoundError("neither main.py nor run.py is present; cannot launch")


def build_command(
    python: str,
    target: Path,
    argv: list[str],
) -> list[str]:
    return [python, str(target), *argv]


def launch(argv: list[str] | None = None, *, exec_target: bool = True) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    wrote = ensure_env(ROOT)
    if wrote is not None:
        print(f"wrote {wrote} from .env.example (DRY_RUN=true, keys empty)", flush=True)
    target = choose_target(ROOT)
    cmd = build_command(sys.executable, target, args)
    via = target.name
    print(
        f"Bitbank BTC/JPY を起動します（対象: {via} / DRY_RUN 既定 / 実注文なし）",
        flush=True,
    )
    print("HOLD/WAIT is normal. Ctrl-C to stop. JSON detail is logs/bot.log", flush=True)
    if not exec_target:
        return 0
    os.execv(cmd[0], cmd)
    return 2


if __name__ == "__main__":
    raise SystemExit(launch())
