"""Enhanced launcher for the existing bitbank_bot entrypoint.

Used by ``start.sh`` and ``python -m bitbank_bot.launch``. Locates the repo
root, loads ``.env`` without printing secrets, prints SET/UNSET diagnostics,
refuses LIVE without dual-auth, and optionally restarts on crash with backoff.

It does not place Bitbank orders. Child process is ``python -m bitbank_bot``.

Do not paste this file or pytest output into zsh. From any cwd::

    bash ./start.sh
    bash /absolute/path/to/start.sh
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from bitbank_bot.config import (
    LIVE_CONFIRM_PHRASE,
    MODE_DRY_RUN,
    MODE_LIVE,
    MODE_LIVE_READY,
    Config,
    ConfigError,
    load_config,
)
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
    }
)
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
    "  cd ~/docker-compose-up-d && bash ./start.sh\n"
    "Or from ~ (no cd): bash ~/docker-compose-up-d/start.sh\n"
    "start.sh is on branch cursor/bitbank-closed-loop-f964 "
    "(git ls-files start.sh must print start.sh).\n"
    "If you are on main, checkout that branch or merge the PR.\n"
    "Do not paste pytest output (.... [ 40%] / 179 passed) into the terminal.\n"
    "Do not run CommandLineTools python3 on test_public.py / main.py from ~.\n"
    "pytest is not a launch step. Tests: bash scripts/run_tests.sh "
    "(absolute path is fine; do not run pytest from ~).\n"
    "If zsh shows a lone '>' prompt, press Ctrl-C, then cd to the repo."
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
    forwarded: list[str]


def looks_like_repo(path: Path) -> bool:
    """True when path is the Bitbank bot checkout (not $HOME)."""
    resolved = path.resolve()
    return (resolved / "src" / "bitbank_bot" / "__init__.py").is_file() and (
        resolved / "run.py"
    ).is_file()


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


def pytest_invocation_guard(
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
        "cannot locate project root (expected src/bitbank_bot and run.py next to start.sh).\n"
        + NOT_IN_REPO_HINT
    )


def ensure_src_on_path(root: Path) -> None:
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
    forwarded: list[str] = []
    for item in raw:
        if item == "--supervise":
            supervise = True
        elif item == "--no-supervise":
            supervise = False
        else:
            forwarded.append(item)
    return LaunchOpts(supervise=supervise, forwarded=forwarded)


def is_oneshot(argv: list[str]) -> bool:
    if any(item in ONESHOT_FLAGS for item in argv):
        return True
    return "--max-cycles" in argv


def under_systemd(environ: dict[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return bool(env.get("INVOCATION_ID"))


def should_supervise(opts: LaunchOpts, environ: dict[str, str] | None = None) -> bool:
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


def apply_cli_dry_run(cfg: Config, forwarded: list[str]) -> Config:
    if "--dry-run" not in forwarded:
        return cfg
    cfg.dry_run = True
    cfg.live_trading = False
    cfg.trading_mode = MODE_DRY_RUN
    cfg.live_trading_confirm = False
    return cfg


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
        f"  BITBANK_API_KEY: {key_status(cfg.api_key)}",
        f"  BITBANK_API_SECRET: {key_status(cfg.api_secret)}",
        f"  may_place_live_orders: {cfg.may_place_live_orders}",
        f"  lock: {lock_text}",
        f"  kill_switch: {kill_text}",
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
    return parser


def _usage_epilog() -> str:
    return (
        "The only supported start from a Mac iTerm prompt:\n"
        "  cd <repo> && bash ./start.sh\n"
        "  bash /absolute/path/to/start.sh\n"
        "  bash ./start.sh --help\n"
        "  bash ./start.sh --once --synthetic --skip-lock --no-screen\n"
        "  bash ./start.sh --check-config\n"
        "RATE_MODE and RECONCILE_EVERY_CYCLES come from .env (printed SET/UNSET, no secrets).\n"
        "LIVE requires TRADING_MODE=LIVE and "
        f"LIVE_TRADING_CONFIRM={LIVE_CONFIRM_PHRASE}. Default is DRY_RUN.\n"
        "If bash says './start.sh: No such file or directory' you are not in the clone "
        "(often ~). cd ~/docker-compose-up-d && bash ./start.sh\n"
        "Optional home-safe wrapper: bash scripts/install_launch_alias.sh\n"
        "If zsh says 'command not found: ....' you pasted pytest dots; press Ctrl-C "
        "if stuck at '>', then cd to the repo and run bash ./start.sh.\n"
        "pytest is not a launch step. Developer tests: "
        "bash scripts/run_tests.sh   or   bash ./start.sh --self-test "
        "(absolute path is fine; do not run pytest from ~).\n"
        "Do not point CommandLineTools python3 at test_public.py / main.py.\n"
        "Do not paste pytest output or this Python source into the terminal.\n"
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
            if item not in {"--self-test", "--supervise", "--no-supervise"}
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
    try:
        cfg = load_config(env_file=env_file_from_argv(opts.forwarded))
    except ConfigError as exc:
        sys.stderr.write(f"launcher: config failed: {exc}\n")
        return 2
    cfg = apply_cli_dry_run(cfg, opts.forwarded)
    allowed, mode, note = evaluate_live_guard(cfg)
    if not allowed:
        sys.stderr.write(f"launcher: {note}\n")
        return 2
    Path(cfg.log_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.lock_path).parent.mkdir(parents=True, exist_ok=True)
    print_diagnostics(
        diagnostics_lines(
            cfg,
            root=root,
            python_exe=resolve_runtime_python(root),
            lock_text=lock_status(Path(cfg.lock_path)),
            kill_text=kill_status(Path(cfg.kill_switch_path)),
            extra_note=note if mode != MODE_DRY_RUN else "",
        )
    )
    if is_oneshot(opts.forwarded) or not should_supervise(opts):
        return int(bot_main(opts.forwarded))
    return supervise_loop(opts.forwarded, root=root, enabled=True)


if __name__ == "__main__":
    raise SystemExit(main())
