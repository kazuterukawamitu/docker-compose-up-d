#!/usr/bin/env python3
"""Clone the GitHub-hosted Bitbank bot, apply corrections, then launch it.

This program does not place orders and does not enable live trading.
It never injects --once unless you pass that flag.

    python3 launch_from_git.py
    python3 launch_from_git.py --once --synthetic --skip-lock
    python3 launch_from_git.py --workdir ~/docker-compose-up-d --ref cursor/bitbank-audit-fixes-cfb4

When this file already lives inside a bot checkout, it uses that tree and does
not change branches. From anywhere else it clones the hosted repo, checks out
the bot ref, applies overrides on top, then execs launch.py / main.py / run.py.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Mapping

DEFAULT_REPO = "https://github.com/kazuterukawamitu/docker-compose-up-d.git"
DEFAULT_REF = "cursor/bitbank-audit-fixes-cfb4"
SCRIPT_ROOT = Path(__file__).resolve().parent

# Applied last, on top of the hosted checkout and any override files.
CORRECTIONS = {
    "DRY_RUN": "true",
    "LIVE_TRADING": "false",
    "BITBANK_PAIR": "btc_jpy",
}

_SECRET_KEY = re.compile(
    r"(secret|token|password|signature|authorization)",
    re.IGNORECASE,
)


def is_bot_tree(root: Path) -> bool:
    return (root / "src" / "bitbank_bot" / "__init__.py").is_file() or (
        root / "run.py"
    ).is_file()


def parse_override_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            raise ValueError(f"override line must be KEY=VALUE: {line!r}")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if not key or not key.isidentifier():
            raise ValueError(f"invalid override key: {key!r}")
        values[key] = value
    return values


def load_override_file(path: Path) -> dict[str, str]:
    return parse_override_env(path.read_text(encoding="utf-8"))


def collect_override_files(
    overrides_dir: Path | None,
    extra_env_files: list[Path],
) -> list[Path]:
    files: list[Path] = []
    if overrides_dir is not None and overrides_dir.is_dir():
        preferred = overrides_dir / "env"
        if preferred.is_file():
            files.append(preferred)
        files.extend(sorted(p for p in overrides_dir.glob("*.env") if p.is_file()))
        local_env = overrides_dir / "local.env"
        if local_env.is_file() and local_env not in files:
            files.append(local_env)
    for path in extra_env_files:
        if path not in files:
            files.append(path)
    return files


def collect_patches(overrides_dir: Path | None, extra_patches: list[Path]) -> list[Path]:
    patches: list[Path] = []
    if overrides_dir is not None and overrides_dir.is_dir():
        patch_dir = overrides_dir / "patches"
        if patch_dir.is_dir():
            patches.extend(sorted(patch_dir.glob("*.patch")))
        patches.extend(sorted(overrides_dir.glob("*.patch")))
    patches.extend(extra_patches)
    return patches


def merge_overrides(files: list[Path]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for path in files:
        merged.update(load_override_file(path))
    return merged


def apply_corrections(env: Mapping[str, str] | None = None) -> dict[str, str]:
    merged = dict(env or {})
    merged.update(CORRECTIONS)
    return merged


def redact_env(env: Mapping[str, str]) -> dict[str, str]:
    safe: dict[str, str] = {}
    for key, value in env.items():
        if key.lower().startswith("has_"):
            safe[key] = value
        elif _SECRET_KEY.search(key) or "api_key" in key.lower():
            safe[key] = "[REDACTED]"
        else:
            safe[key] = value
    return safe


def ensure_dotenv(root: Path) -> Path | None:
    dest = root / ".env"
    example = root / ".env.example"
    if dest.is_file() or not example.is_file():
        return None
    dest.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


def choose_target(root: Path) -> Path:
    launch_py = root / "launch.py"
    if launch_py.is_file():
        return launch_py
    if (root / "src" / "bitbank_bot" / "__init__.py").is_file() and (root / "main.py").is_file():
        return root / "main.py"
    run_py = root / "run.py"
    if run_py.is_file():
        return run_py
    raise FileNotFoundError(f"no launch.py, main.py, or run.py under {root}")


def build_command(python: str, target: Path, argv: list[str]) -> list[str]:
    return [python, str(target), *argv]


def run_git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd is not None else None,
        check=True,
        capture_output=True,
        text=True,
    )


def apply_patches(root: Path, patches: list[Path]) -> None:
    for patch in patches:
        if not patch.is_file():
            raise FileNotFoundError(f"patch not found: {patch}")
        run_git(["apply", "--check", str(patch.resolve())], cwd=root)
        run_git(["apply", str(patch.resolve())], cwd=root)
        print(f"applied patch {patch.name}", flush=True)


def sync_hosted_tree(
    workdir: Path,
    repo: str,
    ref: str,
    *,
    fetch: bool,
    checkout: bool,
) -> None:
    git_dir = workdir / ".git"
    if not git_dir.exists():
        if is_bot_tree(workdir):
            return
        workdir.mkdir(parents=True, exist_ok=True)
        if any(workdir.iterdir()):
            raise RuntimeError(f"workdir {workdir} exists and is not a git checkout")
        print(f"cloning {repo} into {workdir}", flush=True)
        run_git(["clone", repo, str(workdir)])
        fetch = True
        checkout = True
    if fetch:
        print(f"fetching origin {ref}", flush=True)
        run_git(["fetch", "origin", ref], cwd=workdir)
    if checkout:
        print(f"checking out {ref}", flush=True)
        remote = f"origin/{ref}"
        try:
            run_git(["rev-parse", "--verify", remote], cwd=workdir)
            run_git(["checkout", "-B", ref, remote], cwd=workdir)
        except subprocess.CalledProcessError:
            run_git(["checkout", ref], cwd=workdir)
    if not is_bot_tree(workdir):
        raise RuntimeError(
            f"{workdir} has no bot source after sync; main is wiki HTML. "
            f"Use --ref {DEFAULT_REF}"
        )


def parse_args(argv: list[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Launch the GitHub-hosted Bitbank bot with corrections on top"
    )
    parser.add_argument("--repo", default=DEFAULT_REPO, help="git remote URL")
    parser.add_argument("--ref", default=DEFAULT_REF, help="branch or tag to launch")
    parser.add_argument("--workdir", default=None, help="checkout directory")
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="git fetch the hosted ref (default when cloning)",
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="do not git fetch (default inside an existing bot checkout)",
    )
    parser.add_argument(
        "--checkout",
        action="store_true",
        help="allow changing the workdir branch to --ref",
    )
    parser.add_argument(
        "--override-env",
        action="append",
        default=[],
        help="KEY=VALUE file applied on top of the hosted checkout (repeatable)",
    )
    parser.add_argument(
        "--patch",
        action="append",
        default=[],
        help="local unified patch applied on top of the hosted checkout (repeatable)",
    )
    parser.add_argument(
        "--overrides-dir",
        default=None,
        help="directory of env/patch overlays (default: <workdir>/overrides)",
    )
    return parser.parse_known_args(argv)


def resolve_workdir(script_root: Path, workdir: str | None) -> Path:
    if workdir:
        return Path(workdir).expanduser().resolve()
    if is_bot_tree(script_root):
        return script_root
    return (Path.home() / "docker-compose-up-d").resolve()


def launch(argv: list[str] | None = None, *, exec_target: bool = True) -> int:
    ns, forwarded = parse_args(argv)
    workdir = resolve_workdir(SCRIPT_ROOT, ns.workdir)
    inside = is_bot_tree(SCRIPT_ROOT) and workdir == SCRIPT_ROOT.resolve()
    fetch = bool(ns.fetch)
    checkout = bool(ns.checkout)
    if ns.no_fetch:
        fetch = False
    elif not inside and not ns.fetch:
        fetch = not is_bot_tree(workdir)
    if inside and checkout:
        print(
            "refusing in-place checkout of the current bot tree; "
            "pass --workdir to a separate directory",
            file=sys.stderr,
        )
        return 2
    if not inside:
        checkout = checkout or not is_bot_tree(workdir)
        sync_hosted_tree(
            workdir,
            ns.repo,
            ns.ref,
            fetch=fetch,
            checkout=checkout,
        )
    elif fetch:
        sync_hosted_tree(
            workdir,
            ns.repo,
            ns.ref,
            fetch=True,
            checkout=False,
        )

    wrote = ensure_dotenv(workdir)
    if wrote is not None:
        print(f"wrote {wrote} from .env.example (DRY_RUN=true, keys empty)", flush=True)

    overrides_dir = (
        Path(ns.overrides_dir).expanduser().resolve()
        if ns.overrides_dir
        else (workdir / "overrides")
    )
    env_files = collect_override_files(
        overrides_dir if overrides_dir.is_dir() else None,
        [Path(p).expanduser().resolve() for p in ns.override_env],
    )
    patches = collect_patches(
        overrides_dir if overrides_dir.is_dir() else None,
        [Path(p).expanduser().resolve() for p in ns.patch],
    )
    overlay = merge_overrides(env_files)
    overlay = apply_corrections(overlay)
    if patches:
        apply_patches(workdir, patches)
    child_env = dict(os.environ)
    child_env.update(overlay)
    shown = redact_env({key: overlay[key] for key in overlay})
    print(
        f"Git-hosted bot at {workdir} ref={ns.ref} overrides={shown}",
        flush=True,
    )

    target = choose_target(workdir)
    cmd = build_command(sys.executable, target, forwarded)
    print(
        f"Bitbank BTC/JPY を起動します（Git対象: {target.name} / 補正済み DRY_RUN / 実注文なし）",
        flush=True,
    )
    print("HOLD/WAIT is normal. Ctrl-C to stop. JSON detail is logs/bot.log", flush=True)
    if not exec_target:
        return 0
    os.chdir(workdir)
    os.execvpe(cmd[0], cmd, child_env)
    return 2


if __name__ == "__main__":
    raise SystemExit(launch())
