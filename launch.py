#!/usr/bin/env python3
"""Launch the Bitbank BTC/JPY bot without Git.

Uses files next to this script. Does not clone, fetch, checkout, or prompt
for a Git login. If this file is alone, it downloads the public stdlib
DRY_RUN program over HTTPS and runs that. This launcher does not enable
live orders.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
PUBLIC_RUN_PY = (
    "https://raw.githubusercontent.com/kazuterukawamitu/"
    "docker-compose-up-d/cursor/no-git-launcher-8bed/run.py"
)


def _run_module(path: Path, argv: list[str]) -> int:
    spec = importlib.util.spec_from_file_location("bitbank_launch_target", path)
    if spec is None or spec.loader is None:
        sys.stderr.write(f"cannot load {path}\n")
        return 2
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return int(module.main(argv))


def _download_run_py() -> Path | None:
    sys.stderr.write(
        "local bot files missing; downloading public DRY_RUN program over HTTPS (no Git login)\n"
    )
    dest = Path(tempfile.gettempdir()) / "bitbank_run.py"
    req = urllib.request.Request(PUBLIC_RUN_PY, headers={"User-Agent": "bitbank-launch"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
    except (OSError, urllib.error.URLError) as exc:
        sys.stderr.write(f"download failed: {type(exc).__name__}\n")
        return None
    if b"create_order(" in data or b"/user/spot/order" in data:
        sys.stderr.write("refusing downloaded file; unexpected order API\n")
        return None
    if b"def main" not in data:
        sys.stderr.write("refusing downloaded file; not the DRY_RUN program\n")
        return None
    dest.write_bytes(data)
    sys.stderr.write("download complete; starting DRY_RUN screen\n")
    return dest


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    package_ok = (SRC / "bitbank_bot" / "engine.py").is_file() and (ROOT / "main.py").is_file()
    if package_ok:
        try:
            from bitbank_bot.main import main as bot_main

            return int(bot_main(args))
        except ModuleNotFoundError as exc:
            sys.stderr.write(
                f"full package dependency missing ({exc.name}); starting stdlib DRY_RUN\n"
            )
    run_py = ROOT / "run.py"
    if run_py.is_file():
        return _run_module(run_py, args)
    downloaded = _download_run_py()
    if downloaded is None:
        return 2
    return _run_module(downloaded, args)


if __name__ == "__main__":
    raise SystemExit(main())
