"""Enhanced launcher for the existing bitbank_bot entrypoint.

Used by ``start.sh``, ``python -m bitbank_bot.launch``, and ``launch_bot.py``.
Locates the repo root, loads ``.env`` without printing secrets, prints SET/UNSET
diagnostics, refuses LIVE without dual-auth, and optionally restarts on crash
with backoff. ``--print-plan`` prints the start graph (config/engine/orders)
without starting Engine.

It does not place Bitbank orders. Child process is ``python -m bitbank_bot``.

Do not paste this file, JSON logs, or agent reports into zsh. From ~ on a Mac,
paper transaction (one line)::

    bash ~/docker-compose-up-d/run_transaction.sh

Continuous 取引画面 (HOLD is normal)::

    bash ~/docker-compose-up-d/start.sh
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parents[1]
if _SRC_DIR.name == "src":
    _src_s = str(_SRC_DIR)
    if _src_s not in sys.path:
        sys.path.insert(0, _src_s)

from bitbank_bot.config import (
    LIVE_CONFIRM_PHRASE,
    MODE_DRY_RUN,
    MODE_LIVE,
    MODE_LIVE_READY,
    Config,
    ConfigError,
    load_config,
)
from bitbank_bot.main import build_parser as bot_build_parser
from bitbank_bot.main import main as bot_main

ONESHOT_FLAGS = frozenset(
    {
        "--once",
        "--check-config",
        "--preflight",
        "--backtest",
        "--help",
        "-h",
        "--self-test",
        "--execute",
        "--smoke-order",
        "--print-plan",
        "--launch-plan",
    }
)
SMOKE_FLAGS = frozenset({"--execute", "--smoke-order"})
PLAN_FLAGS = frozenset({"--print-plan", "--launch-plan"})
REQUIRED_PROGRAM_FILES = (
    "src/bitbank_bot/__init__.py",
    "src/bitbank_bot/launch.py",
    "src/bitbank_bot/main.py",
    "src/bitbank_bot/engine.py",
    "src/bitbank_bot/orders.py",
    "src/bitbank_bot/config.py",
    "main.py",
    "run.py",
    "start.sh",
)
CHILD_SMOKE = "Engine.run_smoke_order"
CHILD_ONCE = "Engine.run_once"
CHILD_LOOP = "Engine.run_forever"
CHILD_CONFIG = "load_config"
CHILD_PREFLIGHT = "preflight"
CHILD_BACKTEST = "run_backtest"
CHILD_PLAN = "print_launch_plan"
FATAL_EXIT_CODES = frozenset({2, 3})
CLEAN_EXIT_CODES = frozenset({0, 130, 143, -2, -15})
INITIAL_BACKOFF_SEC = 2.0
MAX_BACKOFF_SEC = 30.0
LOG_ROTATION_HINT = "logs/bot.log rotated at 5MB x 5; do not dump huge stdout"
# ASCII-only quotes in this file. U+201C/U+201D in a paste are not from this repo.
SMART_QUOTES = frozenset("\u201c\u201d\u2018\u2019")
NOT_IN_REPO_HINT = (
    "cd to the repo first, then run: bash ./start.sh\n"
    "Typical clone name: docker-compose-up-d\n"
    "Do not paste this chat, JSON logs, agent reports, or script source. "
    "Ctrl-C if you see '>'. Then run ONE of:\n"
    "  bash ~/docker-compose-up-d/run_transaction.sh\n"
    "  bash ~/docker-compose-up-d/start.sh\n"
    "Never bash /workspace/start.sh on a Mac. Uses repo .venv, never ~/.venv.\n"
    "start.sh is on branch cursor/bitbank-closed-loop-f964 "
    "(git ls-files start.sh must print start.sh).\n"
    "If you are on main, checkout that branch or merge the PR.\n"
    "Do not paste pytest output (.... [ 40%] / 179 passed) into the terminal.\n"
    "Do not run CommandLineTools python3 on test_public.py / main.py from ~.\n"
    "pytest is not a launch step. Tests: bash scripts/run_tests.sh "
    "(absolute path is fine; do not run pytest from ~).\n"
    "If zsh shows a lone '>' prompt, press Ctrl-C, then run the one command above."
)
PYTEST_HOME_HINT = (
    "pytest found no Bitbank tests in this directory.\n"
    "cd to the repo or use: bash scripts/run_tests.sh\n"
    "Do not run pytest from ~. pytest is not how you start the bot."
)


class LaunchError(RuntimeError):
    pass


@dataclass(frozen=True)
class LaunchOpts:
    supervise: bool | None
    print_plan: bool
    forwarded: list[str]


CLONE_PATH_HINT = (
    "Clone path: ~/docker-compose-up-d  (branch cursor/bitbank-closed-loop-f964)\n"
    "  git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git "
    "~/docker-compose-up-d\n"
    "  git -C ~/docker-compose-up-d checkout cursor/bitbank-closed-loop-f964\n"
    "Then run ONE line (do not paste this file, JSON logs, or a traceback):\n"
    "  bash ~/docker-compose-up-d/start.sh\n"
    "Paper fill: bash ~/docker-compose-up-d/run_transaction.sh\n"
    "Never bash /workspace/start.sh on a Mac. Never ~/.venv."
)


def looks_like_repo(path: Path) -> bool:
    """True when path is the Bitbank bot checkout (not $HOME)."""
    resolved = path.resolve()
    pkg = resolved / "src" / "bitbank_bot"
    return (
        (pkg / "__init__.py").is_file()
        and (pkg / "launch.py").is_file()
        and (resolved / "run.py").is_file()
    )


def launch_source_path(root: Path) -> Path:
    return (Path(root) / "src" / "bitbank_bot" / "launch.py").resolve()


def missing_launch_message(root: Path | None = None) -> str:
    """Clear clone-path error when launch.py is missing (not a home-venv traceback)."""
    location = str(root) if root is not None else "~/docker-compose-up-d"
    return (
        f"cannot start: missing {location}/src/bitbank_bot/launch.py\n"
        "That is not a bot crash and not a reason to use ~/.venv.\n"
        + CLONE_PATH_HINT
        + "\n"
        + NOT_IN_REPO_HINT
    )


def assert_launch_source(root: Path) -> Path:
    expected = launch_source_path(root)
    if not expected.is_file():
        raise LaunchError(missing_launch_message(root))
    return expected


def verify_bitbank_import(root: Path | None = None) -> int:
    """Confirm this clone's launch.py is importable. Exit 2 with a clone path, not a traceback."""
    try:
        resolved = Path(root) if root is not None else find_project_root()
        expected = assert_launch_source(resolved)
    except LaunchError as exc:
        sys.stderr.write(f"launcher: {exc}\n")
        return 2
    try:
        import bitbank_bot
    except ModuleNotFoundError:
        sys.stderr.write(missing_launch_message(resolved) + "\n")
        return 2
    pkg = Path(bitbank_bot.__file__).resolve().parent
    got = pkg / "launch.py"
    if not got.is_file() or got.resolve() != expected:
        sys.stderr.write(
            f"launcher: imported bitbank_bot is {pkg}, expected {expected.parent}.\n"
            "Use the repo .venv only, never ~/.venv.\n"
        )
        sys.stderr.write(missing_launch_message(resolved) + "\n")
        return 2
    here = Path(__file__).resolve()
    if here.parent != expected.parent or here.stem != "launch":
        sys.stderr.write(f"launcher: running {here}, expected {expected}.\n")
        sys.stderr.write(missing_launch_message(resolved) + "\n")
        return 2
    missing = missing_program_files(resolved)
    if missing:
        sys.stderr.write(
            "launcher: clone is missing program files "
            f"(need main/engine/orders/config/launch): {', '.join(missing)}\n"
        )
        sys.stderr.write(missing_launch_message(resolved) + "\n")
        return 2
    return 0


def missing_program_files(root: Path) -> list[str]:
    """Relative paths that must exist before this launcher starts the bot."""
    resolved = Path(root)
    return [rel for rel in REQUIRED_PROGRAM_FILES if not (resolved / rel).is_file()]


def classify_child_path(forwarded: list[str], *, print_plan: bool = False) -> str:
    """Map CLI flags to the existing bot path (does not start a second bot)."""
    if print_plan:
        return CHILD_PLAN
    if wants_smoke(forwarded):
        return CHILD_SMOKE
    if "--check-config" in forwarded:
        return CHILD_CONFIG
    if "--preflight" in forwarded:
        return CHILD_PREFLIGHT
    if "--backtest" in forwarded:
        return CHILD_BACKTEST
    if "--once" in forwarded:
        return CHILD_ONCE
    return CHILD_LOOP


def launch_plan_lines(
    *,
    root: Path,
    python_exe: str,
    cfg: Config,
    forwarded: list[str],
    supervise: bool,
    print_plan: bool = False,
) -> list[str]:
    """Start graph after parsing config, main, engine, orders, systemd, run.py."""
    child = classify_child_path(forwarded, print_plan=print_plan)
    live = "true" if cfg.may_place_live_orders else "false"
    mode = cfg.resolved_trading_mode()
    flags = " ".join(forwarded).strip()
    child_cmd = f"python -m bitbank_bot{(' ' + flags) if flags else ''}"
    return [
        "LAUNCH_PLAN (one stack; this launcher starts the existing bot)",
        f"  repo: {root}",
        f"  python: {python_exe}",
        f"  mode: {mode} live={live}",
        "  Mac 取引画面:  bash ~/docker-compose-up-d/start.sh",
        "  Mac paper fill: bash ~/docker-compose-up-d/run_transaction.sh",
        "  systemd:        .venv/bin/python -m bitbank_bot.launch "
        "--no-supervise --no-screen",
        "  stdlib fallback: python3 run.py (DRY_RUN, no orders)",
        f"  child: {child_cmd}",
        f"  engine_path: {child}",
        "  program: config.load_config -> Engine -> OrderExecutor",
        "  orders: DRY_RUN never Bitbank POST; LIVE needs dual-auth (not enabled here)",
        f"  supervise: {supervise}",
        "  never ~/.venv; never bash /workspace/start.sh on a Mac",
    ]


def validate_bot_argv(forwarded: list[str]) -> int:
    """Reject unknown flags before Engine/supervise. Exit 2, do not restart."""
    parser = bot_build_parser()
    parser.exit_on_error = False
    try:
        _ns, extra = parser.parse_known_args(list(forwarded))
    except argparse.ArgumentError as exc:
        sys.stderr.write(
            f"launcher: invalid flag for python -m bitbank_bot: {exc}\n"
            "See: bash ./start.sh --help   or   bash ./start.sh --print-plan\n"
        )
        return 2
    except SystemExit as exc:
        code = exc.code
        if code in (None, 0):
            return 0
        sys.stderr.write(
            "launcher: invalid flag for python -m bitbank_bot "
            f"(exit {code}). See: bash ./start.sh --help\n"
        )
        return 2
    if extra:
        sys.stderr.write(
            "launcher: unknown flag(s) for python -m bitbank_bot: "
            f"{' '.join(extra)}\n"
            "See: bash ./start.sh --help   or   bash ./start.sh --print-plan\n"
        )
        return 2
    return 0


def state_status(path: Path) -> str:
    target = Path(path)
    if not target.exists():
        return f"{target} absent"
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return f"{target} present (unreadable)"
    if not isinstance(raw, dict):
        return f"{target} present"
    if raw.get("position"):
        return f"{target} present (saved position; not a crash)"
    if raw.get("pending") and isinstance(raw.get("pending"), dict) and raw["pending"].get(
        "order_id"
    ):
        return f"{target} present (pending order saved)"
    return f"{target} present"


def cwd_is_inside_repo(root: Path, cwd: Path | None = None) -> bool:
    here = (cwd or Path.cwd()).resolve()
    try:
        here.relative_to(root.resolve())
        return True
    except ValueError:
        return False


def looks_like_pytest_paste(argv: list[str]) -> bool:
    """Detect pytest progress (.... [ 40%] / 179 passed) pasted as argv."""
    for item in argv:
        stripped = item.strip()
        if len(stripped) >= 2 and set(stripped) <= {".", " "}:
            return True
        if stripped.startswith("...."):
            return True
        if stripped.startswith("[") and stripped.endswith("]") and "%" in stripped:
            return True
        if stripped in {"passed", "failed", "error"}:
            return True
        if stripped[:1].isdigit() and stripped.endswith("passed"):
            return True
    return False


def resolve_runtime_python(
    root: Path,
    *,
    venv_python: Path | None = None,
    fallback: str | None = None,
    exists_fn=None,
) -> str:
    """Prefer ``<root>/.venv/bin/python``. Never guess the venv from cwd.

    ``exists_fn`` and ``venv_python`` are mockable. CommandLineTools
    ``/usr/bin/python3`` is only the fallback when no venv interpreter exists.
    """
    candidate = Path(venv_python) if venv_python is not None else (root / ".venv" / "bin" / "python")
    check = exists_fn or (lambda p: Path(p).is_file() and os.access(p, os.X_OK))
    if check(candidate):
        return str(candidate)
    return fallback if fallback is not None else sys.executable


def guard_pytest_cwd(
    cwd: Path | None = None,
    *,
    module_file: Path | None = None,
) -> str | None:
    """Error text when pytest is started outside the clone (e.g. from ~)."""
    here = (cwd or Path.cwd()).resolve()
    if looks_like_repo(here):
        return None
    if (here / "tests").is_dir() and looks_like_repo(here.parent):
        return None
    seed = module_file if module_file is not None else Path(__file__)
    try:
        root = find_project_root(seed)
    except LaunchError:
        return PYTEST_HOME_HINT
    if cwd_is_inside_repo(root, here):
        return None
    return (
        f"pytest found no Bitbank tests in this directory (cwd={here}).\n"
        f"cd {root} or use: bash {root}/scripts/run_tests.sh\n"
        "Do not run pytest from ~. pytest is not how you start the bot."
    )


def find_project_root(start: Path | None = None) -> Path:
    """Walk parents until ``src/bitbank_bot`` and ``run.py`` exist. No home-path guess."""
    seen: set[Path] = set()
    seeds: list[Path] = []
    if start is not None:
        seeds.append(start)
    seeds.append(Path.cwd())
    seeds.append(Path(__file__).resolve())
    for seed in seeds:
        cur = seed if seed.is_dir() else seed.parent
        for _ in range(12):
            resolved = cur.resolve()
            if resolved in seen:
                break
            seen.add(resolved)
            if looks_like_repo(resolved):
                return resolved
            if resolved.parent == resolved:
                break
            cur = resolved.parent
    raise LaunchError(
        "cannot locate project root (expected src/bitbank_bot/launch.py and "
        "run.py next to start.sh).\n"
        + missing_launch_message()
    )


def executable_is_home_venv(
    python_exe: str | None = None,
    *,
    home: Path | None = None,
    root: Path | None = None,
) -> bool:
    """True when the interpreter lives in ``~/.venv`` and that is not the repo venv."""
    exe = Path(python_exe or sys.executable).resolve()
    home_venv = (Path(home) if home is not None else Path.home()) / ".venv"
    try:
        home_resolved = home_venv.resolve()
    except OSError:
        return False
    if not home_resolved.exists():
        return False
    try:
        exe.relative_to(home_resolved)
    except ValueError:
        return False
    if root is not None:
        repo_venv = (Path(root) / ".venv").resolve()
        try:
            if exe.relative_to(repo_venv):
                return False
        except ValueError:
            pass
    return True


def ensure_src_on_path(root: Path | None = None) -> None:
    if root is None:
        src_path = Path(__file__).resolve().parents[1]
        root = src_path.parent
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    pythonpath = os.environ.get("PYTHONPATH", "")
    parts = [p for p in pythonpath.split(os.pathsep) if p]
    if src not in parts:
        os.environ["PYTHONPATH"] = src if not pythonpath else src + os.pathsep + pythonpath


def split_launch_argv(argv: list[str] | None) -> LaunchOpts:
    raw = list(sys.argv[1:] if argv is None else argv)
    supervise: bool | None = None
    print_plan = False
    forwarded: list[str] = []
    for item in raw:
        if item == "--supervise":
            supervise = True
        elif item == "--no-supervise":
            supervise = False
        elif item in PLAN_FLAGS:
            print_plan = True
        else:
            forwarded.append(item)
    return LaunchOpts(supervise=supervise, print_plan=print_plan, forwarded=forwarded)


def is_oneshot(argv: list[str]) -> bool:
    if any(item in ONESHOT_FLAGS for item in argv):
        return True
    return "--max-cycles" in argv


def under_systemd(environ: dict[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return bool(env.get("INVOCATION_ID"))


def should_supervise(opts: LaunchOpts, environ: dict[str, str] | None = None) -> bool:
    if opts.print_plan:
        return False
    if is_oneshot(opts.forwarded):
        return False
    if opts.supervise is False:
        return False
    if opts.supervise is True:
        return True
    if under_systemd(environ):
        return False
    return True


def key_status(value: str) -> str:
    return "SET" if bool(value) else "UNSET"


def lock_status(path: Path) -> str:
    if not path.exists():
        return f"{path} absent"
    raw = path.read_text(encoding="utf-8", errors="replace").strip()
    pid_s = raw.split()[0] if raw else ""
    if not pid_s.isdigit():
        return f"{path} present (pid unknown)"
    pid = int(pid_s)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return f"{path} stale pid={pid}"
    except PermissionError:
        return f"{path} pid={pid} (running? permission denied)"
    return f"{path} held pid={pid}"


def kill_status(path: Path) -> str:
    if path.exists():
        return f"{path} PRESENT (new orders halted)"
    return f"{path} absent"


def evaluate_live_guard(cfg: Config) -> tuple[bool, str, str]:
    """Allow start unless resolved mode is LIVE without dual-auth (config should not do that)."""
    mode = cfg.resolved_trading_mode()
    if mode == MODE_LIVE:
        if cfg.live_trading_confirm and cfg.has_keys and not cfg.dry_run:
            return True, mode, "LIVE dual-auth present (real-money risk)"
        return False, mode, "LIVE refused: need TRADING_MODE=LIVE and dual-auth phrase plus keys"
    if mode == MODE_LIVE_READY:
        return True, mode, "LIVE_READY (WOULD_SUBMIT_ORDER only; no POST)"
    return True, mode, "DRY_RUN default (no Bitbank POST)"


def wants_smoke(argv: list[str]) -> bool:
    return any(item in SMOKE_FLAGS for item in argv)


def apply_cli_dry_run(cfg: Config, forwarded: list[str]) -> Config:
    if "--dry-run" not in forwarded and not wants_smoke(forwarded):
        return cfg
    cfg.dry_run = True
    cfg.live_trading = False
    cfg.trading_mode = MODE_DRY_RUN
    cfg.live_trading_confirm = False
    if wants_smoke(forwarded):
        cfg.simulate_fill = True
    return cfg


def launch_ok_line(*, root: Path, python_exe: str, cfg: Config) -> str:
    mode = cfg.resolved_trading_mode()
    live = "true" if cfg.may_place_live_orders else "false"
    return f"LAUNCH_OK repo={root} python={python_exe} mode={mode} live={live}"


def print_launch_ok(*, root: Path, python_exe: str, cfg: Config) -> None:
    line = launch_ok_line(root=root, python_exe=python_exe, cfg=cfg)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def env_file_from_argv(forwarded: list[str]) -> str | None:
    for i, item in enumerate(forwarded):
        if item == "--env-file" and i + 1 < len(forwarded):
            return forwarded[i + 1]
        if item.startswith("--env-file="):
            return item.split("=", 1)[1]
    return None


def diagnostics_lines(
    cfg: Config,
    *,
    root: Path,
    python_exe: str,
    lock_text: str,
    kill_text: str,
    extra_note: str = "",
    engine_path: str = "",
    state_text: str = "",
) -> list[str]:
    mode = cfg.resolved_trading_mode()
    return [
        "Bitbank BTC/JPY launcher (no secrets)",
        f"  project_root: {root}",
        f"  python: {python_exe}",
        f"  TRADING_MODE: {mode}",
        f"  RATE_MODE: {cfg.rate_mode}",
        f"  pair: {cfg.pair}",
        f"  DRY_RUN/LIVE_READY/LIVE: {mode}",
        f"  RECONCILE_EVERY_CYCLES: {cfg.reconcile_every_cycles}",
        f"  CANDLE_TYPE: {cfg.candle_type}",
        f"  simulate_fill: {cfg.simulate_fill}",
        f"  ENABLE_WEBSOCKET: {cfg.enable_websocket}",
        f"  ENABLE_HTF_FILTER: {cfg.enable_htf_filter}",
        f"  POLL_SEC: {cfg.poll_sec}",
        f"  NO_TRADE_TIMEOUT_SECONDS: {cfg.no_trade_timeout_seconds}",
        f"  ORDER_TYPE: {cfg.order_type}",
        f"  BITBANK_API_KEY: {key_status(cfg.api_key)}",
        f"  BITBANK_API_SECRET: {key_status(cfg.api_secret)}",
        f"  may_place_live_orders: {cfg.may_place_live_orders}",
        f"  lock: {lock_text}",
        f"  kill_switch: {kill_text}",
        f"  state: {state_text or cfg.state_path}",
        f"  engine_path: {engine_path or classify_child_path([])}",
        f"  log_dir: {cfg.log_dir} ({LOG_ROTATION_HINT})",
        *( [f"  note: {extra_note}"] if extra_note else [] ),
    ]


def print_diagnostics(lines: list[str]) -> None:
    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()


def classify_exit(rc: int) -> str:
    if rc in CLEAN_EXIT_CODES:
        return "clean"
    if rc in FATAL_EXIT_CODES:
        return "fatal"
    return "crash"


def child_command(forwarded: list[str], *, python_exe: str | None = None) -> list[str]:
    return [python_exe or sys.executable, "-m", "bitbank_bot", *forwarded]


def run_self_test(root: Path, extra: list[str]) -> int:
    """Run pytest from the repo root only. Never a launch step."""
    helper = root / "scripts" / "run_tests.sh"
    if helper.is_file():
        cmd = ["bash", str(helper), *extra]
        proc = subprocess.run(cmd, cwd=str(root))
        return int(proc.returncode)
    env = os.environ.copy()
    src = str(root / "src")
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src if not prev else src + os.pathsep + prev
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *extra],
        cwd=str(root),
        env=env,
    )
    return int(proc.returncode)


def run_child(forwarded: list[str], *, root: Path, python_exe: str | None = None) -> int:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    src = str(root / "src")
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src if not prev else src + os.pathsep + prev
    exe = python_exe or resolve_runtime_python(root)
    proc = subprocess.run(
        child_command(forwarded, python_exe=exe),
        cwd=str(root),
        env=env,
    )
    return int(proc.returncode)


def supervise_loop(
    forwarded: list[str],
    *,
    root: Path,
    enabled: bool,
    sleep_fn=time.sleep,
    run_fn=None,
) -> int:
    runner = run_fn or (lambda args: run_child(args, root=root))
    if not enabled:
        return int(runner(forwarded))
    delay = INITIAL_BACKOFF_SEC
    while True:
        rc = int(runner(forwarded))
        kind = classify_exit(rc)
        if kind == "clean":
            return rc if rc >= 0 else 0
        if kind == "fatal":
            sys.stderr.write(
                f"launcher: fatal exit {rc} (config/lock). Not restarting.\n"
            )
            sys.stderr.flush()
            return rc
        sys.stderr.write(
            f"launcher: crash exit {rc}; restart in {delay:.0f}s "
            "(Ctrl-C to stop; fatal config errors do not loop)\n"
        )
        sys.stderr.flush()
        sleep_fn(delay)
        delay = min(delay * 2, MAX_BACKOFF_SEC)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bitbank-bot-launch",
        description=(
            "Enhanced launcher for the existing Bitbank BTC/JPY bot. "
            "Forwards unknown flags to python -m bitbank_bot."
        ),
        add_help=True,
    )
    parser.add_argument(
        "--supervise",
        action="store_true",
        help="restart on crash with backoff (default for long runs, not under systemd)",
    )
    parser.add_argument(
        "--no-supervise",
        action="store_true",
        help="do not restart (use when systemd Restart=always)",
    )
    parser.add_argument(
        "--print-plan",
        action="store_true",
        help="print the start graph (config/engine/orders) and exit; do not start Engine",
    )
    return parser


def _usage_epilog() -> str:
    return (
        "Do not paste this chat, JSON logs, agent reports, or script source into zsh.\n"
        "Never bash /workspace/start.sh on a Mac. Never ~/.venv.\n"
        "Start graph (this launcher starts the existing bot; it is not a second bot):\n"
        "  continuous 取引画面:  bash ~/docker-compose-up-d/start.sh\n"
        "  paper transaction:    bash ~/docker-compose-up-d/run_transaction.sh\n"
        "  print start graph:    bash ~/docker-compose-up-d/start.sh --print-plan\n"
        "  systemd:              repo .venv python -m bitbank_bot.launch "
        "--no-supervise --no-screen (deploy/bitbank-bot.service)\n"
        "  stdlib fallback:      python3 run.py (no pip; DRY_RUN; no orders)\n"
        "Program this launcher starts (parsed, not rewritten): "
        "config.load_config -> bitbank_bot.main -> Engine -> OrderExecutor.\n"
        "If launch.py is missing, clone ~/docker-compose-up-d on "
        "cursor/bitbank-closed-loop-f964 (do not use ~/.venv).\n"
        "Paper transaction (copy this ONE line; prints SMOKE_ORDER_OK):\n"
        "  bash ~/docker-compose-up-d/run_transaction.sh\n"
        "If the clone exists but may be on the wrong branch:\n"
        "  bash -lc 'cd \"$HOME/docker-compose-up-d\" && git fetch origin "
        "cursor/bitbank-closed-loop-f964 && git checkout cursor/bitbank-closed-loop-f964 "
        "&& exec bash ./run_transaction.sh'\n"
        "Continuous 取引画面 (HOLD/WAIT is normal; not a failed transaction):\n"
        "  bash ~/docker-compose-up-d/start.sh\n"
        "  cd <repo> && bash ./start.sh\n"
        "  bash ./start.sh --help\n"
        "  bash ./start.sh --check-config\n"
        "RATE_MODE and RECONCILE_EVERY_CYCLES come from .env (printed SET/UNSET, no secrets).\n"
        "LIVE requires TRADING_MODE=LIVE and "
        f"LIVE_TRADING_CONFIRM={LIVE_CONFIRM_PHRASE}. Default is DRY_RUN.\n"
        "If bash says './start.sh: No such file or directory' you are not in the clone "
        "(often ~). Use the absolute paths above.\n"
        "Optional home-safe wrapper: bash scripts/install_launch_alias.sh\n"
        "If zsh says 'command not found: ts:' or SMOKE_ORDER_OK / .... you pasted "
        "JSON logs or pytest dots; press Ctrl-C if stuck at '>', then run the one command.\n"
        "pytest is not a launch step. Developer tests: "
        "bash scripts/run_tests.sh   or   bash ./start.sh --self-test "
        "(absolute path is fine; do not run pytest from ~).\n"
        "Do not point CommandLineTools python3 at test_public.py / main.py.\n"
        "Do not paste pytest output, JSON logs, or this Python source into the terminal.\n"
    )


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    opts = split_launch_argv(argv)
    if any(item in {"-h", "--help"} for item in raw):
        build_parser().print_help()
        sys.stdout.write("\n" + _usage_epilog())
        sys.stdout.flush()
        return 0
    if looks_like_pytest_paste(raw):
        sys.stderr.write(
            "launcher: that looks like pytest output pasted into the shell, "
            "not a launcher command.\n"
        )
        sys.stderr.write(NOT_IN_REPO_HINT + "\n")
        return 2
    if "--self-test" in raw:
        extra = [
            item
            for item in raw
            if item
            not in {
                "--self-test",
                "--supervise",
                "--no-supervise",
                "--print-plan",
                "--launch-plan",
            }
        ]
        try:
            root = find_project_root()
        except LaunchError as exc:
            sys.stderr.write(f"launcher: {exc}\n")
            return 2
        os.chdir(root)
        ensure_src_on_path(root)
        return run_self_test(root, extra)
    try:
        root = find_project_root()
    except LaunchError as exc:
        sys.stderr.write(f"launcher: {exc}\n")
        return 2
    if not cwd_is_inside_repo(root):
        sys.stderr.write(
            f"launcher: current directory is not the Bitbank bot repo (cwd={Path.cwd()}).\n"
            f"  repo is at: {root}\n"
            f"  cd {root} && bash ./start.sh\n"
        )
        sys.stderr.write(NOT_IN_REPO_HINT + "\n")
        return 2
    os.chdir(root)
    ensure_src_on_path(root)
    import_rc = verify_bitbank_import(root)
    if import_rc != 0:
        return import_rc
    if executable_is_home_venv(sys.executable, root=root):
        sys.stderr.write(
            "launcher: refusing ~/.venv. Use bash ~/docker-compose-up-d/start.sh "
            "(repo .venv only).\n"
        )
        return 2
    try:
        cfg = load_config(env_file=env_file_from_argv(opts.forwarded))
    except ConfigError as exc:
        sys.stderr.write(f"launcher: config failed: {exc}\n")
        return 2
    if wants_smoke(opts.forwarded) and (
        cfg.may_place_live_orders or cfg.is_live
    ):
        sys.stderr.write(
            "launcher: smoke_order refused: LIVE (no Bitbank POST)\n"
        )
        return 2
    cfg = apply_cli_dry_run(cfg, opts.forwarded)
    allowed, mode, note = evaluate_live_guard(cfg)
    if not allowed:
        sys.stderr.write(f"launcher: {note}\n")
        return 2
    argv_rc = validate_bot_argv(opts.forwarded)
    if argv_rc != 0:
        return argv_rc
    Path(cfg.log_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.lock_path).parent.mkdir(parents=True, exist_ok=True)
    python_exe = resolve_runtime_python(root)
    engine_path = classify_child_path(
        opts.forwarded, print_plan=opts.print_plan
    )
    supervise = should_supervise(opts)
    print_diagnostics(
        diagnostics_lines(
            cfg,
            root=root,
            python_exe=python_exe,
            lock_text=lock_status(Path(cfg.lock_path)),
            kill_text=kill_status(Path(cfg.kill_switch_path)),
            extra_note=note if mode != MODE_DRY_RUN else "",
            engine_path=engine_path,
            state_text=state_status(Path(cfg.state_path)),
        )
    )
    print_launch_ok(root=root, python_exe=python_exe, cfg=cfg)
    if opts.print_plan:
        print_diagnostics(
            launch_plan_lines(
                root=root,
                python_exe=python_exe,
                cfg=cfg,
                forwarded=opts.forwarded,
                supervise=supervise,
                print_plan=True,
            )
        )
        return 0
    if is_oneshot(opts.forwarded) or not supervise:
        return int(bot_main(opts.forwarded))
    return supervise_loop(opts.forwarded, root=root, enabled=True)


if __name__ == "__main__":
    raise SystemExit(main())
