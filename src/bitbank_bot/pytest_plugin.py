"""Pytest plugin: refuse a home-directory / random-cwd collection.

Loaded via ``-p bitbank_bot.pytest_plugin`` (see ``scripts/run_tests.sh``)
or as a pytest11 entry point after ``pip install -e .``. When pytest is
started from ``~`` this prints a cd / run_tests.sh hint instead of
``no tests ran``.
"""

from __future__ import annotations

import sys


def pytest_configure(config) -> None:  # noqa: ARG001
    from bitbank_bot.launch import pytest_invocation_guard

    msg = pytest_invocation_guard()
    if msg:
        sys.stderr.write(msg + "\n")
        raise SystemExit(2)
