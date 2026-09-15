#!/usr/bin/env python3
"""Start the Bitbank btc_jpy closed-loop bot (DRY_RUN by default).

This file cds to the repository root, so it works from any current directory
when invoked by full path:

    python3 ~/docker-compose-up-d/closed_loop.py --go

From ~ on the operator Mac the file is missing until this branch is checked
out. Paste the checkout line in REVIEW / README, then use start.sh --go so
Apple CommandLineTools python is not used without httpx.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

BOT_BRANCH = "cursor/bitbank-closed-loop-1114"
MAC_CLONE = "~/docker-compose-up-d"
MAC_GO = (
    f"cd {MAC_CLONE} && git fetch origin {BOT_BRANCH} && "
    f"git checkout -B {BOT_BRANCH} origin/{BOT_BRANCH} && bash ./start.sh --go"
)

REVIEW = """LAUNCH_OK  Bitbank BTC/JPY closed-loop bot

You are in {cwd}. Python looks for files in the current directory.
Do NOT run python3 closed_loop.py or python3 main.py from ~ (home).
~/main.py is a different Sentry program (BadDsn). ~/closed_loop.py does not exist.
Do NOT type /path/to/... literally. Do NOT run bash ./start.sh from ~ (home finder).

From ~ on this Mac, paste this ONE line (replace nothing):

  {mac_go}

That checks out this branch, creates .venv, installs httpx, runs one DRY_RUN cycle.
HOLD / no_buy_setup is a successful start. No live orders.

Later starts (after the checkout above has succeeded):

  bash ~/docker-compose-up-d/start.sh --go

This copy of the bot is:

  bash {root}/start.sh --go

Continuous 取引画面:

  bash ~/docker-compose-up-d/start.sh --screen
"""


def _stdlib(argv: list[str]) -> int:
    path = ROOT / "run.py"
    spec = importlib.util.spec_from_file_location("bitbank_stdlib_run", path)
    if spec is None or spec.loader is None:
        sys.stderr.write("LAUNCH_FAIL  run.py is missing; cannot start\n")
        return 2
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    forwarded = ["--once", "--synthetic", "--no-screen"]
    extra = [a for a in argv if a.startswith("-") and a not in {"--go", "--once", "--synthetic", "--no-screen", "--dry-run", "--skip-lock"}]
    return int(module.main([*forwarded, *extra]))


def _missing_source() -> int:
    sys.stderr.write(
        "LAUNCH_FAIL  src/bitbank_bot is missing next to this file.\n"
        "You are not in the bot clone, or the clone is still on main / another branch.\n"
        "Paste this ONE line at the ~ prompt:\n"
        f"  {MAC_GO}\n"
    )
    sys.stderr.flush()
    return 2


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if "--review" in args:
        sys.stdout.write(
            REVIEW.format(root=ROOT, cwd=Path.cwd(), mac_go=MAC_GO)
        )
        sys.stdout.flush()
        return 0

    if not (SRC / "bitbank_bot" / "main.py").is_file():
        return _missing_source()

    try:
        from bitbank_bot.boot import announce, prepare_process
    except ModuleNotFoundError:
        return _missing_source()

    prepare_process(ROOT)

    # Bare `python3 closed_loop.py` is the guaranteed start (one DRY_RUN cycle).
    if not args:
        args = ["--go"]

    if "--go" in args:
        announce("LAUNCH_OK  python3 closed_loop.py --go")
        extra = [
            a
            for a in args
            if a
            not in {
                "--go",
                "--once",
                "--synthetic",
                "--dry-run",
                "--skip-lock",
                "--no-screen",
                "--loop",
                "--verify",
                "--no-public",
                "--review",
            }
        ]
        try:
            from bitbank_bot.main import main as bot_main
        except ModuleNotFoundError as exc:
            sys.stderr.write(
                f"full package/deps missing ({exc}); starting stdlib DRY_RUN (run.py)\n"
            )
            return _stdlib(args)
        return int(bot_main(["--go", *extra]))

    if "--loop" in args:
        announce("LAUNCH_OK  python3 closed_loop.py --loop  (Ctrl-C to stop)")
        from bitbank_bot.main import main as bot_main

        rest = [a for a in args if a != "--loop"]
        return int(bot_main(["--loop", "--dry-run", "--skip-lock", "--no-screen", *rest]))

    verify = "--verify" in args
    no_public = "--no-public" in args
    args = [a for a in args if a not in {"--verify", "--no-public", "--review", "--go"}]

    if "--screen" not in args and "--no-screen" not in args:
        args.append("--no-screen")

    if verify:
        forwarded = ["--once", "--skip-lock", "--no-screen", "--dry-run"]
        if no_public:
            forwarded.append("--synthetic")
        forwarded.extend(args)
        announce(
            "LAUNCH_OK  python3 closed_loop.py --verify"
            + (" --no-public" if no_public else "")
        )
        from bitbank_bot.main import main as bot_main

        return int(bot_main(forwarded))

    if no_public:
        sys.stderr.write("--no-public is only valid with --verify or --go\n")
        return 2

    announce("LAUNCH_OK  python3 closed_loop.py  (JSON DRY_RUN loop, Ctrl-C to stop)")
    from bitbank_bot.main import main as bot_main

    return int(bot_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
