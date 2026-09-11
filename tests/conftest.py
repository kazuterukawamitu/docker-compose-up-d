"""Repo pytest hooks. Not a launch step."""

from __future__ import annotations


def pytest_configure(config) -> None:  # noqa: ARG001
    import pytest

    from bitbank_bot.launch import guard_pytest_cwd

    msg = guard_pytest_cwd()
    if msg:
        pytest.exit(msg, returncode=2)
