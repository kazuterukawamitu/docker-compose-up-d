#!/usr/bin/env bash
# One-shot DRY_RUN wrapper. Not a second bot. Does not POST live orders.
# cds to this repo via BASH_SOURCE, then execs the existing start.sh.
if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
exec bash "$ROOT/start.sh" --once --skip-lock --no-screen "$@"
