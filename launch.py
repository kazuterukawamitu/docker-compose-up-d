#!/usr/bin/env python3
"""Enhanced Bitbank BTC/JPY program launcher.

This is the program that starts every other program. Default is a continuous
DRY_RUN 取引画面. Live POST /user/spot/order happens only when keys exist and
live mode is requested (see docs/MASTER_REQUIREMENTS.md). Never prints secrets.

    python3 launch.py
    python3 launch.py --doctor
    python3 launch.py --check
    python3 launch.py --live-ready
    python3 launch.py --live

`start.sh` execs this file after venv setup. `main.py` is an alias of this
file. Stdlib fallback is `run.py` (DRY_RUN only; never create_order).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

LIVE_CONFIRM_OK = "YES_I_ACCEPT_REAL_MONEY_RISK"
REEXEC_ENV = "BITBANK_LAUNCHER_REEXEC"
PUBLIC_TICKER_URL = "https://public.bitbank.cc/btc_jpy/ticker"

# How every program in this repo is started. launch.py is the only starter
# that applies mode banners, venv re-exec, and the stdlib fallback.
PROGRAMS: tuple[tuple[str, str], ...] = (
    ("launch.py", "canonical starter (this file)"),
    ("start.sh", "Mac/VPS wrapper: venv, pip, .env, exec launch.py"),
    ("main.py", "alias of launch.py; same flags and modes"),
    ("run.py", "stdlib DRY_RUN 取引画面; never create_order"),
    ("src/bitbank_bot/main.py", "package CLI after launch.py (or python -m bitbank_bot)"),
    ("diagnostics.py", "JSON env probe; no secrets"),
    ("scripts/bitbank_execution_audit.py", "read-only public/private audit; no orders"),
)

REQUIRED_FILES: tuple[str, ...] = (
    "launch.py",
    "main.py",
    "run.py",
    "start.sh",
    "src/bitbank_bot/__init__.py",
    "src/bitbank_bot/engine.py",
    "src/bitbank_bot/strategy.py",
    "src/bitbank_bot/orders.py",
    "src/bitbank_bot/rest_client.py",
    "src/bitbank_bot/main.py",
    "src/bitbank_bot/config.py",
    "src/bitbank_bot/execution_gate.py",
)

_STDLIB_DROP_FLAGS = frozenset(
    {
        "--check",
        "--check-config",
        "--preflight",
        "--backtest",
        "--live",
        "--live-ready",
        "--doctor",
        "--programs",
    }
)
_STDLIB_DROP_VALUE = frozenset({"--env-file"})


def _ensure_stdio() -> None:
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _ensure_dirs() -> None:
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "data").mkdir(exist_ok=True)


def _ensure_env_file() -> None:
    env_path = ROOT / ".env"
    example = ROOT / ".env.example"
    if env_path.exists() or not example.is_file():
        return
    env_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    print(
        "LAUNCHER copied .env.example -> .env (DRY_RUN remains true; keys empty)",
        file=sys.stderr,
        flush=True,
    )


def _venv_python() -> Path | None:
    for name in ("bin/python3", "bin/python"):
        path = ROOT / ".venv" / name
        if path.is_file():
            return path
    return None


def _has_httpx() -> bool:
    return importlib.util.find_spec("httpx") is not None


def _reexec_venv_if_needed() -> None:
    if os.environ.get(REEXEC_ENV) == "1":
        return
    if _has_httpx():
        return
    venv_py = _venv_python()
    if venv_py is None:
        return
    try:
        if venv_py.resolve() == Path(sys.executable).resolve():
            return
    except OSError:
        pass
    os.environ[REEXEC_ENV] = "1"
    os.execv(str(venv_py), [str(venv_py), str(ROOT / "launch.py"), *sys.argv[1:]])


def _read_dotenv(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def _has_keys(file_env: dict[str, str]) -> bool:
    key = (os.environ.get("BITBANK_API_KEY") or file_env.get("BITBANK_API_KEY") or "").strip()
    secret = (
        os.environ.get("BITBANK_API_SECRET") or file_env.get("BITBANK_API_SECRET") or ""
    ).strip()
    return bool(key) and bool(secret)


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def filter_stdlib_argv(argv: list[str]) -> list[str]:
    """Keep flags that run.py understands; drop package-only / launcher flags."""
    out: list[str] = []
    skip_value = False
    for item in argv:
        if skip_value:
            skip_value = False
            continue
        if item in _STDLIB_DROP_VALUE:
            skip_value = True
            continue
        if item.startswith("--env-file="):
            continue
        if item in _STDLIB_DROP_FLAGS:
            continue
        out.append(item)
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="launch.py",
        description="Start the Bitbank BTC/JPY bot (DRY_RUN unless --live + keys)",
        epilog=(
            "Also: python3 main.py (alias). start.sh (venv then this file). "
            "Forwarded to the bot: --once --synthetic --screen --no-screen "
            "--skip-lock --dry-run --max-cycles --preflight --check-config "
            "--backtest --env-file."
        ),
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="enable live orders for this process if API keys are present",
    )
    parser.add_argument(
        "--live-ready",
        action="store_true",
        help="full live path except POST /user/spot/order (WOULD_SUBMIT_ORDER)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="alias for --check-config",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="self-check programs, files, mode, and public ticker; then exit",
    )
    parser.add_argument(
        "--programs",
        action="store_true",
        help="print the program map and exit",
    )
    parser.add_argument("--env-file", default=None, help="optional .env path")
    return parser


def _split_argv(argv: list[str] | None) -> tuple[argparse.Namespace, list[str]]:
    parser = build_parser()
    args, rest = parser.parse_known_args(argv)
    if args.check:
        rest = ["--check-config", *rest]
    if args.env_file:
        rest = ["--env-file", args.env_file, *rest]
    return args, rest


def _apply_mode(args: argparse.Namespace, file_env: dict[str, str]) -> str:
    if args.live and args.live_ready:
        sys.stderr.write("choose one of --live or --live-ready\n")
        raise SystemExit(2)
    if args.live:
        if not _has_keys(file_env):
            sys.stderr.write(
                "LIVE refused: BITBANK_API_KEY / BITBANK_API_SECRET missing. "
                "Put keys in .env locally. Never paste them into chat.\n"
            )
            raise SystemExit(2)
        confirm = (
            os.environ.get("LIVE_TRADING_CONFIRM")
            or file_env.get("LIVE_TRADING_CONFIRM")
            or ""
        ).strip()
        if confirm and confirm != LIVE_CONFIRM_OK:
            sys.stderr.write(
                "LIVE_TRADING_CONFIRM is set but not YES_I_ACCEPT_REAL_MONEY_RISK; "
                "degrading to LIVE_READY (no POST /user/spot/order).\n"
            )
            os.environ["DRY_RUN"] = "true"
            os.environ["LIVE_TRADING"] = "false"
            os.environ["LIVE_READY"] = "true"
            os.environ["TRADING_MODE"] = "live_ready"
            return "live_ready"
        os.environ["DRY_RUN"] = "false"
        os.environ["LIVE_TRADING"] = "true"
        os.environ["LIVE_READY"] = "false"
        os.environ["TRADING_MODE"] = "live"
        return "live"
    if args.live_ready:
        os.environ["DRY_RUN"] = "true"
        os.environ["LIVE_TRADING"] = "false"
        os.environ["LIVE_READY"] = "true"
        os.environ["TRADING_MODE"] = "live_ready"
        return "live_ready"
    if _truthy(os.environ.get("LIVE_READY") or file_env.get("LIVE_READY")):
        return "live_ready"
    dry = os.environ.get("DRY_RUN", file_env.get("DRY_RUN", "true"))
    live = os.environ.get("LIVE_TRADING", file_env.get("LIVE_TRADING", "false"))
    if not _truthy(dry) and _truthy(live):
        return "live"
    return "dry_run"


def _banner(mode: str, has_keys: bool) -> None:
    live_orders = mode == "live" and has_keys
    print("Bitbank BTC/JPY launcher", flush=True)
    print(f"TRADING_MODE={mode}", flush=True)
    print(f"DRY_RUN={os.environ.get('DRY_RUN', '')}", flush=True)
    print(f"LIVE_TRADING={os.environ.get('LIVE_TRADING', '')}", flush=True)
    print(f"LIVE_READY={os.environ.get('LIVE_READY', '')}", flush=True)
    print(f"has_api_keys={str(has_keys).lower()}", flush=True)
    print(f"may_place_live_orders={str(live_orders).lower()}", flush=True)
    if live_orders:
        print("LIVE: BUY/SELL setups will call Bitbank create_order", flush=True)
    else:
        print("no Bitbank create_order on this process unless mode=live and keys", flush=True)


def _print_programs() -> int:
    print("Bitbank BTC/JPY programs", flush=True)
    for name, role in PROGRAMS:
        print(f"{name}: {role}", flush=True)
    print("canonical_starter=launch.py", flush=True)
    print("pair=btc_jpy", flush=True)
    print("default_mode=dry_run", flush=True)
    return 0


def _public_ticker() -> dict[str, object]:
    result: dict[str, object] = {"ok": False, "url": PUBLIC_TICKER_URL}
    try:
        if _has_httpx():
            import httpx

            response = httpx.get(PUBLIC_TICKER_URL, timeout=15)
            result["http_status"] = response.status_code
            body = response.json()
        else:
            request = urllib.request.Request(PUBLIC_TICKER_URL, method="GET")
            with urllib.request.urlopen(request, timeout=15) as response:
                result["http_status"] = getattr(response, "status", 200)
                body = json.loads(response.read().decode("utf-8"))
        result["ok"] = body.get("success") == 1
        last = str((body.get("data") or {}).get("last") or "")
        result["has_last_price"] = bool(last)
        if last:
            result["last"] = last
    except (OSError, urllib.error.URLError, TimeoutError, ValueError, Exception) as exc:
        result["ok"] = False
        result["error"] = type(exc).__name__
    return result


def _package_config_ok() -> tuple[bool, str]:
    try:
        from bitbank_bot.config import PAIR, load_config

        cfg = load_config()
        if cfg.pair != PAIR:
            return False, f"pair={cfg.pair}"
        return True, f"pair={cfg.pair} trading_mode={cfg.trading_mode}"
    except Exception as exc:
        return False, type(exc).__name__


def _doctor(mode: str, has_keys: bool) -> int:
    print("DOCTOR Bitbank BTC/JPY launcher", flush=True)
    print(f"python={sys.version.split()[0]}", flush=True)
    print(f"executable={sys.executable}", flush=True)
    print(f"root={ROOT}", flush=True)
    print(f"httpx={str(_has_httpx()).lower()}", flush=True)
    print(f"venv_python={_venv_python() or 'none'}", flush=True)
    print(f"TRADING_MODE={mode}", flush=True)
    print(f"has_api_keys={str(has_keys).lower()}", flush=True)
    print(f"may_place_live_orders={str(mode == 'live' and has_keys).lower()}", flush=True)
    print("pair=btc_jpy", flush=True)
    missing = [name for name in REQUIRED_FILES if not (ROOT / name).is_file()]
    if missing:
        print(f"required_files=FAIL missing={','.join(missing)}", flush=True)
        rc = 2
    else:
        print("required_files=ok", flush=True)
        rc = 0
    env_present = (ROOT / ".env").is_file()
    print(f"env_file={'present' if env_present else 'missing (using process env / defaults)'}", flush=True)
    for name, role in PROGRAMS:
        exists = (ROOT / name).is_file()
        print(f"program {name}={'ok' if exists else 'MISSING'} ({role})", flush=True)
        if not exists:
            rc = 2
    if sys.version_info < (3, 9):
        print("python_version=FAIL need 3.9+", flush=True)
        rc = 2
    else:
        print("python_version=ok", flush=True)
    ticker = _public_ticker()
    if ticker.get("ok"):
        print(
            f"public_ticker=ok last={ticker.get('last', '')} http={ticker.get('http_status', '')}",
            flush=True,
        )
    else:
        print(
            f"public_ticker=WARN error={ticker.get('error', '')} http={ticker.get('http_status', '')}",
            flush=True,
        )
    if _has_httpx() and importlib.util.find_spec("bitbank_bot") is not None:
        ok, detail = _package_config_ok()
        print(f"package_config={'ok' if ok else 'FAIL'} {detail}", flush=True)
        if not ok:
            rc = 2
    else:
        print("package_config=skipped (httpx or package missing; DRY_RUN fallback is run.py)", flush=True)
    print("secrets=not printed", flush=True)
    print(f"doctor={'ok' if rc == 0 else 'FAIL'}", flush=True)
    return rc


def _stdlib_dry_run(rest: list[str]) -> int:
    path = ROOT / "run.py"
    spec = importlib.util.spec_from_file_location("bitbank_stdlib_run", path)
    if spec is None or spec.loader is None:
        sys.stderr.write("run.py is missing; cannot start DRY_RUN fallback\n")
        return 2
    print("full package/deps missing; starting stdlib DRY_RUN (run.py, no orders)", flush=True)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return int(module.main(filter_stdlib_argv(rest)))


def _load_file_env(env_file: str | None) -> tuple[Path, dict[str, str]]:
    path = Path(env_file).expanduser() if env_file else ROOT / ".env"
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    file_env = _read_dotenv(path)
    try:
        from dotenv import load_dotenv
    except ImportError:
        for key, val in file_env.items():
            os.environ.setdefault(key, val)
    else:
        load_dotenv(path, override=False)
    return path, file_env


def main(argv: list[str] | None = None) -> int:
    _ensure_stdio()
    if argv is None:
        _reexec_venv_if_needed()
    _ensure_dirs()
    args, rest = _split_argv(argv)
    if args.programs:
        return _print_programs()
    if args.env_file is None:
        _ensure_env_file()
    _path, file_env = _load_file_env(args.env_file)
    try:
        mode = _apply_mode(args, file_env)
    except SystemExit as exc:
        return int(exc.code or 2)

    has_keys = _has_keys(file_env)
    if args.doctor:
        return _doctor(mode, has_keys)

    _banner(mode, has_keys)

    try:
        import httpx  # noqa: F401
        from bitbank_bot.main import main as package_main
    except ModuleNotFoundError:
        if mode in {"live", "live_ready"}:
            sys.stderr.write(
                f"{mode} needs httpx (pip install -r requirements.txt). "
                "Refusing to start a second live client.\n"
            )
            return 2
        if args.check or "--check-config" in rest or "--preflight" in rest:
            return _doctor(mode, has_keys)
        if "--backtest" in rest:
            sys.stderr.write("backtest needs the full package and httpx\n")
            return 2
        return _stdlib_dry_run(rest)
    return int(package_main(rest))


if __name__ == "__main__":
    raise SystemExit(main())
