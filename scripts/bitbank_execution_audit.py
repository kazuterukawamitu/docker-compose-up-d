#!/usr/bin/env python3
"""Read-only Bitbank execution audit. Never places orders."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bitbank_bot.audit import run_audit  # noqa: E402
from bitbank_bot.config import load_config  # noqa: E402
from bitbank_bot.logging_setup import setup_logging  # noqa: E402
from bitbank_bot.rest_client import RestClient  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    cfg = load_config()
    setup_logging(cfg.log_dir, cfg.log_level, secrets=[cfg.api_secret, cfg.api_key])
    rest = RestClient(
        public_url=cfg.public_url,
        private_url=cfg.private_url,
        api_key=cfg.api_key,
        api_secret=cfg.api_secret,
        access_time_window_ms=cfg.access_time_window_ms,
        timeout_sec=cfg.http_timeout_sec,
        max_retries=cfg.max_retries,
        query_rps=cfg.query_rps,
        update_rps=cfg.update_rps,
    )
    try:
        report = run_audit(cfg, rest)
    finally:
        rest.close()
    print(json.dumps(report.as_dict(), indent=2))
    return 0 if report.consistent else 2


if __name__ == "__main__":
    raise SystemExit(main())
