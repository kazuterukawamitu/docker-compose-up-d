#!/usr/bin/env python3
"""The program you start. Bitbank BTC/JPY bot launcher.

    python3 launch.py
    python3 main.py
    bash start.sh

Default is a continuous DRY_RUN 取引画面. This file never enables LIVE.
It never prints API secrets. Stop with Ctrl-C.

    python3 launch.py --doctor          # environment check, then exit
    python3 launch.py --once --synthetic --no-screen --skip-lock
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

LAUNCH_BANNER = "Bitbank BTC/JPY 起動プログラム"


def _utf8_stdio() -> None:
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _ensure_src_path() -> None:
    src = str(SRC)
    if src not in sys.path:
        sys.path.insert(0, src)
    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def prepare_runtime() -> list[str]:
    """Create logs/data and a DRY_RUN .env if missing. Never overwrite .env."""
    notes: list[str] = []
    for name in ("logs", "data"):
        path = ROOT / name
        path.mkdir(parents=True, exist_ok=True)
        notes.append(f"dir={name}")
    env_path = ROOT / ".env"
    example = ROOT / ".env.example"
    if not env_path.is_file() and example.is_file():
        env_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        notes.append("wrote_.env_from_example")
    return notes


def _stdlib_run(argv: list[str]) -> int:
    path = ROOT / "run.py"
    spec = importlib.util.spec_from_file_location("bitbank_stdlib_run", path)
    if spec is None or spec.loader is None:
        sys.stderr.write("run.py is missing; cannot start\n")
        return 2
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return int(module.main(argv))


def _has_full_package() -> bool:
    if not (SRC / "bitbank_bot" / "__init__.py").is_file():
        return False
    try:
        import httpx  # noqa: F401
        from bitbank_bot.main import main as _main  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True


def _print_banner(*, entry: str, argv: Sequence[str]) -> None:
    print(LAUNCH_BANNER, flush=True)
    print(
        f"entry={entry}  pair=btc_jpy  default=DRY_RUN  live_orders=off_until_armed",
        flush=True,
    )
    print(f"python={sys.executable}  version={sys.version.split()[0]}", flush=True)
    if argv:
        print("args=" + " ".join(argv), flush=True)


def run_launcher(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    _ensure_src_path()
    raw = list(sys.argv[1:] if argv is None else argv)

    if "--version" in raw:
        version = "0.1.0"
        try:
            from bitbank_bot import __version__ as pkg_version

            version = str(pkg_version)
        except Exception:
            pass
        print(f"bitbank-btc-jpy-bot {version}", flush=True)
        return 0

    if "--doctor" in raw:
        notes = prepare_runtime()
        _print_banner(entry="doctor", argv=["--doctor"])
        print("prepare=" + ",".join(notes), flush=True)
        try:
            import diagnostics

            return int(diagnostics.main())
        except Exception as exc:
            sys.stderr.write(f"doctor failed: {type(exc).__name__}\n")
            return 2

    notes = prepare_runtime()
    forwarded = [a for a in raw if a not in {"--doctor", "--version"}]
    if _has_full_package():
        _print_banner(entry="full_package", argv=forwarded)
        print("prepare=" + ",".join(notes), flush=True)
        from bitbank_bot.main import main as package_main

        return int(package_main(forwarded))

    sys.stderr.write("full package/deps missing; starting stdlib DRY_RUN (run.py)\n")
    _print_banner(entry="stdlib_run.py", argv=forwarded)
    print("prepare=" + ",".join(notes), flush=True)
    return _stdlib_run(forwarded)


def main(argv: list[str] | None = None) -> int:
    try:
        return run_launcher(argv)
    except KeyboardInterrupt:
        print("\nstopped", flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
