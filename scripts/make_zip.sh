#!/usr/bin/env bash
# Deliverable zip (requested). Also: FORMAT=tar.gz bash scripts/make_archive.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export FORMAT=zip
exec bash "$ROOT/scripts/make_archive.sh" "$@"
