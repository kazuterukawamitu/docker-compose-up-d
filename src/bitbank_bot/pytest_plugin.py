"""Pytest plugin: refuse a home-directory / random-cwd collection.

Loaded via ``-p bitbank_bot.pytest_plugin`` (see ``scripts/run_tests.sh``)
or as a pytest11 entry point after ``pip install -e .``. When pytest is
started from ``~`` this prints a cd / run_tests.sh hint instead of
``no tests ran``.
"""

from __future__ import annotations


def pytest_configure(config) -> None:  # noqa: ARG001
    import pytest

    from bitbank_bot.launch import guard_pytest_cwd

    msg = guard_pytest_cwd()
    if msg:
        pytest.exit(msg, returncode=2)
