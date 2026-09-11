#!/usr/bin/env bash
# Developer tests only. This is NOT how you start the bot.
# Always cds to the repo that contains this script (never uses ~ as src).
#
#   cd <repo> && bash scripts/run_tests.sh
#   bash /absolute/path/to/scripts/run_tests.sh
#   bash ./start.sh --self-test
#
# Do not paste this into zsh at ~. Do not paste pytest dots back into the terminal.
# Do not run CommandLineTools python3 -m pytest from ~ (that is "no tests ran").

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/.." && pwd)"

if [[ ! -f "$root/start.sh" || ! -f "$root/src/bitbank_bot/launch.py" || ! -d "$root/tests" ]]; then
  echo "cd to the repo first, then run: bash scripts/run_tests.sh" >&2
  echo "Or: bash /absolute/path/to/scripts/run_tests.sh" >&2
  echo "This is not a launch command. Launch is: bash /path/to/start.sh" >&2
  echo "Typical clone: cd ~/docker-compose-up-d && bash ./start.sh" >&2
  echo "Do not run pytest from ~ (that is \"no tests ran\")." >&2
  exit 2
fi

cd "$root"
export PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}"

choose_pytest_python() {
  local c path_dir
  if [[ -x "$root/.venv/bin/python" ]] && \
     "$root/.venv/bin/python" -c "import pytest" >/dev/null 2>&1; then
    echo "$root/.venv/bin/python"
    return 0
  fi
  # Walk PATH so a leading /usr/bin/python3 without pytest does not win.
  local IFS=:
  for path_dir in ${PATH:-}; do
    [[ -n "$path_dir" ]] || continue
    for c in "$path_dir/python3" "$path_dir/python"; do
      if [[ -x "$c" ]] && "$c" -c "import pytest" >/dev/null 2>&1; then
        echo "$c"
        return 0
      fi
    done
  done
  return 1
}

if ! PY="$(choose_pytest_python)"; then
  echo "pytest is not installed. From the repo: python3 -m pip install -e '.[dev]'" >&2
  echo "Still not a launch step. The bot is: bash ./start.sh" >&2
  echo "Do not run CommandLineTools python3 -m pytest from ~." >&2
  exit 2
fi

has_target=0
for a in "$@"; do
  case "$a" in
    -*)
      ;;
    *)
      has_target=1
      ;;
  esac
done

# Always collect tests/ unless the caller already named a path.
# -p prints a clear error if this script is ever invoked with cwd ~= home
# without the cd above (should not happen).
if [[ "$has_target" -eq 0 ]]; then
  exec "$PY" -m pytest -p bitbank_bot.pytest_plugin tests "$@"
fi
exec "$PY" -m pytest -p bitbank_bot.pytest_plugin "$@"
