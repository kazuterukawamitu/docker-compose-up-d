#!/usr/bin/env bash
# Compatibility wrapper. Prefer tar.gz (zip-free) via make_archive.sh.
# Usage: bash scripts/make_zip.sh [out_dir]
#        FORMAT=tar.xz bash scripts/make_zip.sh [out_dir]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export FORMAT="${FORMAT:-tar.gz}"
exec bash "$ROOT/scripts/make_archive.sh" "$@"
