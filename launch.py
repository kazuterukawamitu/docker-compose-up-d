#!/usr/bin/env python3
"""The program you start. Bitbank BTC/JPY bot launcher.

Run this from the git checkout, or copy this file anywhere (including ~).
If the bot source is missing, it looks under ~/docker-compose-up-d and
clones the repository there. It never enables LIVE. It never prints secrets.
It never runs ~/main.py (that file on a Mac is often a different program).

    python3 launch.py
    bash start.sh

Stop with Ctrl-C. Do not paste comments (# ...) on the same command line.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

LAUNCH_BANNER = "Bitbank BTC/JPY 起動プログラム"
REPO_URL = "https://github.com/kazuterukawamitsu/docker-compose-up-d.git"
REPO_DIRNAME = "docker-compose-up-d"
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff\u00a0"), None)

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"


def clean_argv(argv: Sequence[str]) -> list[str]:
    """Drop zero-width / NBSP characters that Mac paste often inserts."""
    cleaned: list[str] = []
    for raw in argv:
        item = str(raw).translate(_INVISIBLE).strip()
        if item:
            cleaned.append(item)
    return cleaned


def looks_like_bot(path: Path) -> bool:
    root = Path(path)
    return (root / "src" / "bitbank_bot" / "__init__.py").is_file() and (
        (root / "launch.py").is_file() or (root / "run.py").is_file()
    )


def candidate_roots() -> list[Path]:
    home = Path.home()
    cwd = Path.cwd()
    found: list[Path] = []
    env_root = (os.environ.get("BITBANK_BOT_ROOT") or "").strip()
    if env_root:
        found.append(Path(env_root).expanduser())
    found.extend(
        [
            Path(__file__).resolve().parent,
            cwd,
            cwd / REPO_DIRNAME,
            home / REPO_DIRNAME,
            home / "Documents" / REPO_DIRNAME,
            home / "src" / REPO_DIRNAME,
        ]
    )
    ordered: list[Path] = []
    seen: set[Path] = set()
    for item in found:
        try:
            resolved = item.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        ordered.append(resolved)
    return ordered


def clone_destination() -> Path:
    override = (os.environ.get("BITBANK_BOT_ROOT") or "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / REPO_DIRNAME


def missing_checkout_message() -> str:
    dest = clone_destination()
    return (
        "Bitbank ボットのソースが見つかりません。ホーム (~) で python3 launch.py や "
        "python3 main.py を実行すると、別のプログラムが動きます。\n"
        "~/main.py は Sentry など別アプリのことがあります。実行しないでください。\n"
        "iTerm に次を 1 行ずつ貼り付けてください:\n"
        f"  git clone {REPO_URL}\n"
        f"  cd {REPO_DIRNAME}\n"
        "  bash start.sh\n"
        f"clone 先の目安: {dest}\n"
        "Apple の python3 が 3.9 のときは brew install python@3.12 のあと "
        "/opt/homebrew/bin/python3.12 launch.py\n"
    )


def _git_clone(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "clone", "--depth", "1", REPO_URL, str(dest)]
    branch = (os.environ.get("BITBANK_BOT_BRANCH") or "").strip()
    if branch:
        cmd = ["git", "clone", "--depth", "1", "--branch", branch, REPO_URL, str(dest)]
    print(f"cloning {REPO_URL} -> {dest}", flush=True)
    subprocess.check_call(cmd)


def resolve_bot_root(*, allow_clone: bool = True) -> Path | None:
    for path in candidate_roots():
        if looks_like_bot(path):
            return path
    if not allow_clone:
        return None
    if (os.environ.get("BITBANK_NO_CLONE") or "").strip() in {"1", "true", "yes"}:
        return None
    dest = clone_destination()
    if looks_like_bot(dest):
        return dest.resolve()
    if dest.exists() and any(dest.iterdir()):
        sys.stderr.write(
            f"{dest} exists but is not the Bitbank bot checkout. "
            "Move it aside or set BITBANK_BOT_ROOT.\n"
        )
        return None
    git = shutil.which("git")
    if git is None:
        return None
    try:
        _git_clone(dest)
    except (OSError, subprocess.CalledProcessError) as exc:
        sys.stderr.write(f"git clone failed: {exc}\n")
        return None
    if looks_like_bot(dest):
        return dest.resolve()
    return None


def apply_root(path: Path) -> None:
    global ROOT, SRC
    ROOT = path.resolve()
    SRC = ROOT / "src"
    os.chdir(ROOT)


def _python312_candidates() -> list[str]:
    names = [
        "/opt/homebrew/bin/python3.12",
        "/usr/local/bin/python3.12",
        "python3.12",
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
    ]
    found: list[str] = []
    for name in names:
        path = name if name.startswith("/") else shutil.which(name)
        if path:
            found.append(path)
    return found


def _interpreter_is_312(executable: str) -> bool:
    try:
        out = subprocess.check_output(
            [
                executable,
                "-c",
                "import sys; print(sys.version_info.major, sys.version_info.minor)",
            ],
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    parts = out.split()
    if len(parts) < 2:
        return False
    major, minor = int(parts[0]), int(parts[1])
    return major > 3 or (major == 3 and minor >= 12)


def reexec_python312_if_needed(argv: list[str]) -> None:
    if sys.version_info >= (3, 12):
        return
    if (os.environ.get("BITBANK_LAUNCH_PYTHON_OK") or "").strip():
        return
    script = str(Path(__file__).resolve())
    for candidate in _python312_candidates():
        if Path(candidate).resolve() == Path(sys.executable).resolve():
            continue
        if not _interpreter_is_312(candidate):
            continue
        env = os.environ.copy()
        env["BITBANK_LAUNCH_PYTHON_OK"] = "1"
        print(
            f"Apple/CommandLineTools python is {sys.version.split()[0]}; "
            f"re-exec {candidate}",
            flush=True,
        )
        os.execve(candidate, [candidate, script, *argv], env)


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
    root = str(ROOT)
    for path in (src, root):
        if path in sys.path:
            sys.path.remove(path)
    sys.path.insert(0, root)
    sys.path.insert(0, src)


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
    except ModuleNotFoundError as exc:
        sys.stderr.write(f"full package/deps missing ({exc}); starting stdlib DRY_RUN (run.py)\n")
        return False
    return True


def _print_banner(*, entry: str, argv: Sequence[str]) -> None:
    print(LAUNCH_BANNER, flush=True)
    print(
        f"entry={entry}  pair=btc_jpy  default=DRY_RUN  live_orders=off_until_armed",
        flush=True,
    )
    print(f"python={sys.executable}  version={sys.version.split()[0]}", flush=True)
    print(f"root={ROOT}", flush=True)
    if argv:
        print("args=" + " ".join(argv), flush=True)


def _bootstrap(argv: list[str]) -> list[str]:
    _utf8_stdio()
    argv = clean_argv(argv)
    reexec_python312_if_needed(argv)
    here = Path(__file__).resolve().parent
    if looks_like_bot(here):
        apply_root(here)
        _ensure_src_path()
        return argv
    root = resolve_bot_root(allow_clone=True)
    if root is None:
        sys.stderr.write(missing_checkout_message())
        raise SystemExit(2)
    target = root / "launch.py"
    if target.is_file() and target.resolve() != Path(__file__).resolve():
        print(f"using checkout {root}", flush=True)
        os.chdir(root)
        os.execv(sys.executable, [sys.executable, str(target), *argv])
    apply_root(root)
    _ensure_src_path()
    return argv


def run_launcher(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    raw = _bootstrap(raw)

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

    if not (ROOT / "run.py").is_file():
        sys.stderr.write(missing_checkout_message())
        return 2
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
