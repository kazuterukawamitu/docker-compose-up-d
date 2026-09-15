#!/usr/bin/env python3
"""Start the Bitbank btc_jpy closed-loop bot (DRY_RUN by default).

This file cds to the repository root, so it works from any current directory:

    python3 closed_loop.py --go

`--go` prints LAUNCH_OK, runs one synthetic DRY_RUN cycle, and exits.
No Bitbank POST. HOLD/no_buy_setup is normal.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bitbank_bot.boot import announce, prepare_process

REVIEW = """LAUNCH_OK  Bitbank BTC/JPY closed-loop bot

Command that always starts (any current directory):

  python3 closed_loop.py --go

If this file is not in the current directory, use the full path:

  python3 {root}/closed_loop.py --go

That prints LAUNCH_OK, runs one DRY_RUN cycle, and exits.

Continuous JSON loop (Ctrl-C to stop):

  python3 closed_loop.py --loop

iTerm 取引画面:

  bash {root}/start.sh --screen
"""


def main(argv: list[str] | None = None) -> int:
    prepare_process(ROOT)
    args = list(sys.argv[1:] if argv is None else argv)

    if "--review" in args:
        sys.stdout.write(REVIEW.format(root=ROOT))
        sys.stdout.flush()
        return 0

    # Bare `python3 closed_loop.py` is the guaranteed start (one DRY_RUN cycle).
    if not args:
        args = ["--go"]

    if "--go" in args:
        announce("LAUNCH_OK  python3 closed_loop.py --go")
        from bitbank_bot.main import main as bot_main

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
