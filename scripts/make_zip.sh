#!/usr/bin/env bash
# Compatibility wrapper. Deliverable is tar.gz (zip以外) by default.
#   bash scripts/make_zip.sh
#   FORMAT=tar.xz bash scripts/make_zip.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export FORMAT="${FORMAT:-tar.gz}"
exec bash "$ROOT/scripts/make_archive.sh" "$@"
