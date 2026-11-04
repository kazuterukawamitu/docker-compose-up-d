#!/usr/bin/env bash
# compileall + pytest + ruff (safe select). Does not enable LIVE.
set -euo pipefail
cd "$(dirname "$0")/.."
export DRY_RUN=true
export LIVE_TRADING=false
exec python3 scripts/quality_pipeline.py
