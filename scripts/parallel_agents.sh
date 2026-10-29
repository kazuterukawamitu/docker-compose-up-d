#!/usr/bin/env bash
# Parallel verification "builder" (Pareto: critical scanners first).
# Analogous to a parallelized webpack pass — runs independent agents together.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p logs
python3 scripts/gap_agent.py | tee logs/gap_agent.out &
p1=$!
python3 scripts/bug_scan.py | tee logs/bug_scan.out &
p2=$!
python3 scripts/purpose_index.py | tee logs/purpose_index.out &
p3=$!
fail=0
wait "$p1" || fail=1
wait "$p2" || fail=1
wait "$p3" || fail=1
echo "parallel_agents done fail=$fail"
exit "$fail"
