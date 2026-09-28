#!/usr/bin/env python3
"""Start the Bitbank BTC/JPY bot without a Git login.

Looks for the project next to this file and in a few known directories.
If those copies are incomplete, downloads the public repository archive
over HTTPS. This program never runs git, never prompts for credentials,
and never places a Bitbank order.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

BRANCH = "cursor/git-free-launch-fa47"
REPO = "kazuterukawamitu/docker-compose-up-d"
ARCHIVE_URLS = (
    "https://codeload.github.com/" + REPO + "/tar.gz/refs/heads/" + BRANCH,
    "https://codeload.github.com/" + REPO + "/tar.gz/refs/heads/main",
)
RUN_URLS = (
    "https://raw.githubusercontent.com/" + REPO + "/" + BRANCH + "/run.py",
    "https://raw.githubusercontent.com/" + REPO + "/main/run.py",
)
RAW_LAUNCH_URL = (
    "https://raw.githubusercontent.com/" + REPO + "/" + BRANCH + "/launch.py"
)
INSTALL_DIR_NAME = "bitbank-btc-jpy-bot"
MAX_ARCHIVE_BYTES = 80_000_000
MAX_RUN_BYTES = 1_000_000

REQUIRED = (
    "main.py",
    "run.py",
    "requirements.txt",
    ".env.example",
    "src/bitbank_bot/__init__.py",
    "src/bitbank_bot/main.py",
)

_LAUNCHER_FLAGS = {"--check", "--no-venv", "--no-download"}
_NO_SCREEN = {
    "--once",
    "--check-config",
    "--preflight",
    "--backtest",
    "--no-screen",
    "--screen",
}


def _say(status: str, step: str, detail: str = "") -> None:
    line = "LAUNCH " + status + " " + step
    if detail:
        line = line + " " + detail
    print(line, flush=True)


def _has_bot(path: Path) -> bool:
    return all((path / rel).is_file() for rel in REQUIRED)


def _candidates(script_dir: Path) -> list[Path]:
    found: list[Path] = []
    env_root = os.environ.get("BITBANK_BOT_ROOT", "").strip()
    if env_root:
        found.append(Path(env_root).expanduser())
    found.append(script_dir)
    found.extend(script_dir.parents)
    home = Path.home()
    found.append(home / "docker-compose-up-d")
    found.append(home / INSTALL_DIR_NAME)
    found.append(home / "bitbank-bot")
    found.append(Path("/home/rocky/bitbank-bot"))
    return found


def find_project(script_dir: Path) -> Path | None:
    seen: set[Path] = set()
    for raw in _candidates(script_dir):
        try:
            path = raw.resolve()
        except OSError:
            continue
        if path in seen:
            continue
        seen.add(path)
        if _has_bot(path) or (path / "run.py").is_file():
            return path
    return None


def _safe_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members: list[tarfile.TarInfo] = []
    for member in archive.getmembers():
        parts = Path(member.name).parts
        if not parts or parts[0] in {"", ".", ".."}:
            continue
        if any(part in {"", ".", ".."} for part in parts):
            continue
        if member.issym() or member.islnk():
            continue
        members.append(member)
    return members


def _read_url(url: str, limit: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "bitbank-launch"})
    with urllib.request.urlopen(request, timeout=180) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > limit:
            raise RuntimeError("download is larger than the limit")
        payload = response.read(limit + 1)
    if len(payload) > limit:
        raise RuntimeError("download is larger than the limit")
    if not payload:
        raise RuntimeError("empty download")
    return payload


def _fresh_dir(preferred: Path) -> Path:
    """Pick a directory without deleting anything already on disk."""
    if not preferred.exists():
        return preferred
    if _has_bot(preferred) or (preferred / "run.py").is_file():
        return preferred
    sibling = preferred.parent / (preferred.name + "-src")
    if not sibling.exists():
        return sibling
    if _has_bot(sibling) or (sibling / "run.py").is_file():
        return sibling
    return Path(tempfile.mkdtemp(prefix="bitbank-bot-", dir=str(preferred.parent)))


def _extract_bot(payload: bytes, dest: Path) -> Path:
    if dest.exists() and _has_bot(dest):
        return dest.resolve()
    final = _fresh_dir(dest)
    if final.exists() and _has_bot(final):
        return final.resolve()
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="bitbank-src-"))
    try:
        archive_path = tmp / "src.tar.gz"
        archive_path.write_bytes(payload)
        with tarfile.open(archive_path, "r:gz") as archive:
            members = _safe_members(archive)
            try:
                archive.extractall(tmp, members=members, filter="data")
            except TypeError:
                archive.extractall(tmp, members=members)
        extracted = [path for path in tmp.iterdir() if path.is_dir() and _has_bot(path)]
        if not extracted:
            raise RuntimeError("downloaded archive has no bot files")
        if final.exists():
            raise RuntimeError("refusing to replace existing directory")
        shutil.move(str(extracted[0]), str(final))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return final.resolve()


def _accept_run_py(payload: bytes) -> str:
    text = payload.decode("utf-8")
    if 'PAIR = "btc_jpy"' not in text or "def main" not in text:
        raise RuntimeError("downloaded run.py is not the Bitbank DRY_RUN bot")
    if "create_order(" in text or "/user/spot/order" in text:
        raise RuntimeError("downloaded run.py is not order-free")
    return text


def _write_run_py(payload: bytes, dest: Path) -> Path:
    text = _accept_run_py(payload)
    final = _fresh_dir(dest)
    final.mkdir(parents=True, exist_ok=True)
    target = final / "run.py"
    if not target.exists():
        target.write_text(text, encoding="utf-8")
    return final.resolve()


def download_project(dest: Path) -> Path:
    """Download the public tree over HTTPS. Never calls git or deletes files."""
    if dest.exists() and (_has_bot(dest) or (dest / "run.py").is_file()):
        return dest.resolve()
    errors: list[str] = []
    for url in ARCHIVE_URLS:
        try:
            found = _extract_bot(_read_url(url, MAX_ARCHIVE_BYTES), dest)
        except (OSError, RuntimeError, tarfile.TarError, UnicodeError, ValueError) as exc:
            errors.append(type(exc).__name__)
            _say("FAIL", "https_archive", type(exc).__name__)
            continue
        _say("PASS", "https_download", "git_login=not_required")
        return found
    for url in RUN_URLS:
        try:
            found = _write_run_py(_read_url(url, MAX_RUN_BYTES), dest)
        except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
            errors.append(type(exc).__name__)
            _say("FAIL", "https_run_py", type(exc).__name__)
            continue
        _say("PASS", "https_download", "stdlib_run_py git_login=not_required")
        return found
    raise RuntimeError("https download failed: " + ",".join(errors))


def _flag(root: Path, name: str, default: str) -> str:
    if name in os.environ and os.environ[name].strip():
        return os.environ[name].strip()
    env_path = root / ".env"
    if not env_path.is_file():
        return default
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip().strip("'\"") or default
    return default


def _python_score(executable: str) -> tuple[int, int]:
    try:
        out = subprocess.check_output(
            [
                executable,
                "-c",
                "import sys; print(sys.version_info[0], sys.version_info[1])",
            ],
            text=True,
            timeout=15,
        ).strip().split()
        major, minor = int(out[0]), int(out[1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return (0, 0)
    if major < 3 or (major == 3 and minor < 9):
        return (0, 0)
    return (major, minor)


def _best_python() -> str:
    names = [
        "/opt/homebrew/bin/python3.12",
        "/usr/local/bin/python3.12",
        "/opt/homebrew/bin/python3.11",
        "/usr/local/bin/python3.11",
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
        "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3",
        "/usr/bin/python3",
        "python3.12",
        "python3.11",
        "python3.10",
        "python3",
        sys.executable,
    ]
    best = sys.executable
    best_score = _python_score(sys.executable)
    seen: set[str] = set()
    for name in names:
        resolved = shutil.which(name) if "/" not in name else name
        if not resolved or resolved in seen:
            continue
        if not Path(resolved).is_file():
            continue
        seen.add(resolved)
        score = _python_score(resolved)
        if score > best_score:
            best = resolved
            best_score = score
    return best


def _deps_ok(root: Path) -> bool:
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        import dotenv  # noqa: F401
        import httpx  # noqa: F401
        from bitbank_bot.main import main as _main  # noqa: F401
    except ModuleNotFoundError as exc:
        _say("FAIL", "import", exc.name or "missing module")
        return False
    return True


def _ensure_venv(root: Path, no_venv: bool) -> None:
    if no_venv or os.environ.get("BITBANK_LAUNCH_PY") == "1":
        return
    if _deps_ok(root):
        _say("PASS", "dependencies", "already installed")
        return
    venv_dir = root / ".venv"
    venv_py = venv_dir / "bin" / "python"
    _say("PASS", "venv", str(venv_dir))
    if not venv_py.is_file():
        try:
            subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])
        except subprocess.CalledProcessError:
            subprocess.check_call(
                [sys.executable, "-m", "venv", "--without-pip", str(venv_dir)]
            )
    if not venv_py.is_file():
        raise OSError("venv python missing")
    subprocess.check_call(
        [
            str(venv_py),
            "-m",
            "pip",
            "install",
            "-q",
            "-r",
            str(root / "requirements.txt"),
        ]
    )
    os.environ["BITBANK_LAUNCH_PY"] = "1"
    os.environ["BITBANK_BOT_ROOT"] = str(root)
    script = str(Path(__file__).resolve())
    os.execv(str(venv_py), [str(venv_py), script, *sys.argv[1:]])


def _ensure_env_file(root: Path) -> None:
    dest = root / ".env"
    example = root / ".env.example"
    if dest.exists() or not example.is_file():
        return
    shutil.copyfile(example, dest)
    _say("PASS", "env_file", "wrote .env from .env.example")


def _forwarded(argv: list[str]) -> list[str]:
    args = [item for item in argv if item not in _LAUNCHER_FLAGS]
    if any(item in _NO_SCREEN for item in args):
        return args
    if sys.stdout.isatty():
        return ["--screen", *args]
    return args


def _run_stdlib(root: Path, argv: list[str]) -> int:
    import importlib.util

    path = root / "run.py"
    spec = importlib.util.spec_from_file_location("bitbank_stdlib_run", path)
    if spec is None or spec.loader is None:
        _say("FAIL", "stdlib DRY_RUN", "run.py missing")
        return 2
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return int(module.main(argv))


def _pick_newer_python() -> None:
    if os.environ.get("BITBANK_PY_PICKED") == "1":
        return
    best = _best_python()
    os.environ["BITBANK_PY_PICKED"] = "1"
    if os.path.realpath(best) == os.path.realpath(sys.executable):
        return
    _say("PASS", "python", best)
    script = str(Path(__file__).resolve())
    os.execv(best, [best, script, *sys.argv[1:]])


def _print_manual_start() -> None:
    print(
        "Git login is not required. Paste this one line in iTerm:",
        file=sys.stderr,
        flush=True,
    )
    print(
        "curl -fsSL -o \"$HOME/bitbank_launch.py\" "
        + RAW_LAUNCH_URL
        + " && python3 \"$HOME/bitbank_launch.py\"",
        file=sys.stderr,
        flush=True,
    )
    print(
        "Or, if that file is missing, this line starts the DRY_RUN screen from main:",
        file=sys.stderr,
        flush=True,
    )
    print(
        "curl -fsSL -o \"$HOME/bitbank_run.py\" " + RUN_URLS[-1] + " && python3 \"$HOME/bitbank_run.py\"",
        file=sys.stderr,
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    check_only = "--check" in args
    no_venv = "--no-venv" in args
    no_download = "--no-download" in args
    if argv is None:
        _pick_newer_python()

    script_dir = Path(__file__).resolve().parent
    root = find_project(script_dir)
    if root is None and not no_download and argv is None:
        try:
            root = download_project(Path.home() / INSTALL_DIR_NAME)
        except (OSError, RuntimeError, tarfile.TarError) as exc:
            _say("FAIL", "https_download", type(exc).__name__)
            root = None
    if root is None or not (_has_bot(root) or (root / "run.py").is_file()):
        _say("FAIL", "local_sources", "bot files not found")
        _print_manual_start()
        return 2
    stdlib_only = not _has_bot(root)

    os.chdir(root)
    os.environ["BITBANK_BOT_ROOT"] = str(root)
    _say("PASS", "project_root", str(root))
    _say("PASS", "local_sources")
    _say("PASS", "git_login", "not_required")

    dry = _flag(root, "DRY_RUN", "true")
    live = _flag(root, "LIVE_TRADING", "false")
    _say("PASS", "trading_mode", "DRY_RUN=%s LIVE_TRADING=%s" % (dry, live))
    print(
        "This launcher does not enable live orders and does not call Bitbank create_order.",
        flush=True,
    )

    forwarded = _forwarded(args)
    if stdlib_only:
        _say("PASS", "start", "run.py")
        fallback = ["--once", "--synthetic", "--no-screen"] if check_only else forwarded
        return _run_stdlib(root, fallback)

    if argv is None:
        try:
            _ensure_venv(root, no_venv)
        except (OSError, subprocess.SubprocessError) as exc:
            _say("FAIL", "venv", type(exc).__name__)

    if not check_only:
        _ensure_env_file(root)

    forwarded = _forwarded(args)
    src = str(root / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    previous = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"] = src + (os.pathsep + previous if previous else "")
    os.environ["PYTHONUNBUFFERED"] = "1"

    if not _deps_ok(root):
        _say("FAIL", "dependencies", "stdlib DRY_RUN via run.py")
        fallback = ["--once", "--synthetic", "--no-screen"] if check_only else forwarded
        return _run_stdlib(root, fallback)

    from bitbank_bot.main import main as bot_main

    if check_only:
        code = int(bot_main(["--check-config", "--no-screen"]))
        _say("PASS" if code == 0 else "FAIL", "check_config", "exit=%s" % code)
        return code

    _say("PASS", "start", "main.py")
    return int(bot_main(forwarded))


if __name__ == "__main__":
    raise SystemExit(main())
