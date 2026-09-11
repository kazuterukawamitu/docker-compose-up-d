"""Repo pytest hooks. Not a launch step."""

from __future__ import annotations

import sys


def pytest_configure(config) -> None:  # noqa: ARG001
    from bitbank_bot.launch import guard_pytest_cwd

    msg = guard_pytest_cwd()
    if msg:
        sys.stderr.write(msg + "\n")
        raise SystemExit(2)
