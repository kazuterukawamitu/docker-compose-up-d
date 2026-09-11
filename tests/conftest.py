"""Repo pytest hooks. Not a launch step."""

from __future__ import annotations

import sys

from bitbank_bot.launch import pytest_invocation_guard


def pytest_configure(config) -> None:  # noqa: ARG001
    msg = pytest_invocation_guard()
    if msg:
        sys.stderr.write(msg + "\n")
        raise SystemExit(2)
