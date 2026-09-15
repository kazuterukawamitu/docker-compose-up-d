#!/usr/bin/env bash
# Enhanced Bitbank BTC/JPY launcher (Mac iTerm + Sakura VPS).
#
# Always cds to the repo that contains THIS file (BASH_SOURCE), never $PWD.
# From the clone, or from ~ via absolute path:
#   cd <repo> && bash ./start.sh
#   bash /absolute/path/to/start.sh
#   bash ./start.sh --help
#
# Do not paste this file, JSON bot logs, agent reports, or script source
# into the terminal. Ctrl-C if you see a lone '>'. Then run ONLY:
#   bash ~/docker-compose-up-d/start.sh
# Never bash /workspace/start.sh on a Mac (that path is the cloud VM).
# This launcher uses $ROOT/.venv/bin/python only, never ~/.venv.
#
# First-time clone (paste this ONE line, not pytest output or JSON logs):
#   bash -lc 'REPO="$HOME/docker-compose-up-d"; set -euo pipefail; if [ ! -d "$REPO/.git" ]; then git clone https://github.com/kazuterukawamitu/docker-compose-up-d.git "$REPO"; fi; cd "$REPO"; git fetch origin cursor/bitbank-closed-loop-f964; git checkout -B cursor/bitbank-closed-loop-f964 origin/cursor/bitbank-closed-loop-f964; exec bash ./start.sh --screen'
#
# Locates this repo (no hardcoded /Users/... path), creates .venv if needed,
# prefers .venv/bin/python (never CommandLineTools python when a venv exists),
# loads .env without printing secrets, then starts the existing bot entrypoint.
# Do not paste python3 main.py. Do not paste pytest dots. Do not paste JSON.
# Do not run /usr/bin/python3 on a random file (test_public.py, ~/main.py).

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail
# Interactive zsh history expansion is NOT disabled by this (do not paste
# this file into zsh). These only affect this bash process.
set +H 2>/dev/null || true
set +o histexpand 2>/dev/null || true

# Prefer Homebrew on Mac, then the caller PATH (CI hosted Python). Do not
# put /usr/bin first — that shadows Actions' python and breaks --self-test.
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-}:/usr/bin:/bin"
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8

usage() {
  cat <<'EOF'
Usage: bash /path/to/start.sh [options]
       cd <repo> && bash ./start.sh [options]

Enhanced launcher for the existing Bitbank BTC/JPY bot (DRY_RUN by default).
This is the program-launching program. It cds to the repo from BASH_SOURCE
(so cwd may be ~). Either cd, or pass the absolute path.

Do not paste JSON logs, agent reports, or script source into the terminal. Ctrl-C if you see '>'. Then run ONLY:
  bash ~/docker-compose-up-d/start.sh
Never bash /workspace/start.sh on a Mac (that path is the cloud VM).
Uses the repo .venv only, never ~/.venv. Branch cursor/bitbank-closed-loop-f964.

  bash ./start.sh
  bash ~/docker-compose-up-d/start.sh
  bash ./start.sh --help
  bash ./start.sh --once --synthetic --skip-lock --no-screen
  bash ./start.sh --check-config
  bash ./start.sh --no-supervise
  bash ./start.sh --supervise
  bash ./start.sh --self-test

If bash says: ./start.sh: No such file or directory
  You ran ./start.sh from ~ (relative path). Use the absolute path or cd:
    bash ~/docker-compose-up-d/start.sh
    cd ~/docker-compose-up-d && bash ./start.sh
  Confirm branch cursor/bitbank-closed-loop-f964:
    git ls-files start.sh
  Optional home-safe finder (so cd ~ && bash ./start.sh prints this hint):
    bash scripts/install_launch_alias.sh
  Do not use CommandLineTools python3 on test_public.py / main.py from ~.

Locates the repo from this script (not a hardcoded Mac path), uses $ROOT/.venv,
writes bitbank_bot_src.pth, loads .env without printing secrets, prints SET/UNSET
diagnostics (RATE_MODE, RECONCILE_EVERY_CYCLES, keys SET/UNSET), and restarts
on crash with backoff (not on config/lock failures). systemd already restarts:
pass --no-supervise (or run python -m bitbank_bot).

LIVE requires TRADING_MODE=LIVE and LIVE_TRADING_CONFIRM=YES_I_ACCEPT_REAL_MONEY_RISK.
Rotated JSON logs live under logs/bot.log (5MB x 5). Ctrl-C stops. data/KILL halts new orders.
Other flags pass through to python -m bitbank_bot.

If zsh says: command not found: ts: / SMOKE_ORDER_OK / FAILURE / compileall: / HOW / LIVE / ....
  You pasted JSON bot logs, pytest progress, or an agent report, not a crash.
  Press Ctrl-C to leave a stuck '>' prompt, then run ONLY:
    bash ~/docker-compose-up-d/start.sh
  If zsh says event not found, you pasted script source (a shebang bang).
  Do not paste JSON logs, agent reports, pytest output, or this file.

pytest is not a launch step. Developer tests (script cds to the repo):
  bash scripts/run_tests.sh
  bash /path/to/scripts/run_tests.sh
  bash ./start.sh --self-test
  Do not run pytest from ~ (that is "no tests ran").
EOF
}

suggest_clones() {
  echo "Typical clone name: docker-compose-up-d" >&2
  echo "  cd ~/docker-compose-up-d" >&2
  echo "  git checkout cursor/bitbank-closed-loop-f964" >&2
  echo "  git ls-files start.sh    # must print: start.sh" >&2
  echo "  bash ./start.sh" >&2
  echo "Or from ~: bash ~/docker-compose-up-d/start.sh" >&2
  echo "If start.sh is missing, you are on main or not in the clone." >&2
  local names="docker-compose-up-d docker-compose-up-d.git bitbank-bot"
  local b n p
  if [[ -n "${HOME:-}" ]]; then
    for b in "$HOME" "$HOME/src" "$HOME/code" "$HOME/dev" "$HOME/Projects" "$HOME/github" "$HOME/repos"; do
      for n in $names; do
        p="$b/$n"
        if [[ -f "$p/start.sh" && -f "$p/src/bitbank_bot/launch.py" ]]; then
          echo "Found a clone at: $p" >&2
          echo "  cd $p && bash ./start.sh" >&2
        fi
      done
    done
  fi
}

not_in_repo() {
  echo "cd to the repo first, then run: bash ./start.sh" >&2
  suggest_clones
  echo "Do not paste JSON logs, agent reports, or script source into the terminal. Ctrl-C if you see '>'. Then run ONLY:" >&2
  echo "  bash ~/docker-compose-up-d/start.sh" >&2
  echo "Never bash /workspace/start.sh on a Mac. Uses repo .venv, never ~/.venv." >&2
  echo "Do not paste pytest output (.... [ 40%] / 179 passed) into the terminal." >&2
  echo "pytest is not a launch step. Do not paste test commands at ~." >&2
  echo "If zsh shows a lone '>' prompt, press Ctrl-C, then run the one command above." >&2
}

resolve_root() {
  local src="${BASH_SOURCE[0]}"
  while [[ -L "$src" ]]; do
    local dir
    dir="$(cd "$(dirname "$src")" && pwd)"
    src="$(readlink "$src")"
    [[ "$src" != /* ]] && src="$dir/$src"
  done
  cd "$(dirname "$src")" && pwd
}

ROOT="$(resolve_root)"
cd "$ROOT"

home_now="$(cd "${HOME:-/}" && pwd -P 2>/dev/null || true)"
if [[ -n "$home_now" && "$ROOT" == "$home_now" ]]; then
  echo "start.sh must live inside the cloned repo, not your home directory." >&2
  not_in_repo
  exit 2
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

for a in "$@"; do
  if [[ "$a" =~ ^\.+$ ]] || [[ "$a" =~ ^\[[[:space:]]*[0-9]+%\]$ ]] || [[ "$a" == "passed" || "$a" == "failed" ]]; then
    echo "That looks like pytest output pasted into the shell, not a launcher command." >&2
    not_in_repo
    exit 2
  fi
done

BOT_BRANCH="cursor/bitbank-closed-loop-f964"

ensure_bot_source() {
  if [[ -f "$ROOT/src/bitbank_bot/__init__.py" && -f "$ROOT/src/bitbank_bot/launch.py" && -f "$ROOT/main.py" ]]; then
    return 0
  fi
  echo "bot source not found at $ROOT (need src/bitbank_bot/launch.py next to start.sh)" >&2
  if [[ ! -d "$ROOT/.git" ]]; then
    not_in_repo
    exit 2
  fi
  echo "fetching $BOT_BRANCH so the trading screen can start" >&2
  git fetch origin "$BOT_BRANCH"
  git checkout -B "$BOT_BRANCH" "origin/$BOT_BRANCH"
  if [[ ! -f "$ROOT/src/bitbank_bot/__init__.py" || ! -f "$ROOT/src/bitbank_bot/launch.py" || ! -f "$ROOT/main.py" ]]; then
    echo "still no bitbank_bot after checkout; branch may not be fetched" >&2
    not_in_repo
    exit 2
  fi
}

ensure_bot_source

self_test=0
self_test_args=()
for a in "$@"; do
  if [[ "$a" == "--self-test" ]]; then
    self_test=1
  else
    self_test_args+=("$a")
  fi
done
if [[ "$self_test" -eq 1 ]]; then
  if [[ ! -f "$ROOT/scripts/run_tests.sh" ]]; then
    echo "cd to the repo first, then run: bash scripts/run_tests.sh" >&2
    not_in_repo
    exit 2
  fi
  if [[ ${#self_test_args[@]} -eq 0 ]]; then
    exec bash "$ROOT/scripts/run_tests.sh"
  fi
  exec bash "$ROOT/scripts/run_tests.sh" "${self_test_args[@]}"
fi

abs_file() {
  local p="$1"
  if [[ -e "$p" ]]; then
    echo "$(cd "$(dirname "$p")" && pwd -P)/$(basename "$p")"
  else
    echo "$p"
  fi
}

is_disallowed_home_venv() {
  local cand abs home_abs root_abs
  cand="$1"
  root_abs="$(cd "$ROOT" && pwd -P)"
  if [[ "$cand" == */* ]]; then
    abs="$cand"
  else
    abs="$(command -v "$cand" 2>/dev/null || true)"
  fi
  [[ -n "$abs" && -e "$abs" ]] || return 1
  abs="$(abs_file "$abs")"
  if [[ -n "${HOME:-}" ]]; then
    home_abs="$(cd "$HOME" && pwd -P 2>/dev/null || true)"
    if [[ -n "$home_abs" && "$home_abs" != "$root_abs" ]]; then
      case "$abs" in
        "$home_abs"/.venv/*)
          return 0
          ;;
      esac
    fi
  fi
  return 1
}

pick_python() {
  local c path_dir rest
  for c in \
    /opt/homebrew/bin/python3.12 \
    /usr/local/bin/python3.12 \
    /opt/homebrew/bin/python3 \
    /usr/local/bin/python3
  do
    if [[ -x "$c" ]] && ! is_disallowed_home_venv "$c"; then
      echo "$c"
      return 0
    fi
  done
  rest="${PATH:-}"
  while [[ -n "$rest" ]]; do
    path_dir="${rest%%:*}"
    if [[ "$rest" == *:* ]]; then
      rest="${rest#*:}"
    else
      rest=""
    fi
    [[ -n "$path_dir" ]] || continue
    for c in python3.12 python3 python; do
      if [[ -x "$path_dir/$c" ]] && ! is_disallowed_home_venv "$path_dir/$c"; then
        echo "$path_dir/$c"
        return 0
      fi
    done
  done
  echo "python3 not found. On a Mac: brew install python@3.12" >&2
  echo "Do not use ~/.venv. This launcher creates and uses $ROOT/.venv only." >&2
  return 1
}

# Prefer $ROOT/.venv/bin/python. Do not run the bot with
# /Library/Developer/CommandLineTools/usr/bin/python3 when a venv exists.
# Never exec a cwd-relative main.py / test_public.py (Errno 2 on Mac).
# Never ~/.venv (that is the home venv; ModuleNotFoundError bitbank_bot).
VENV="$ROOT/.venv"
VPY="$VENV/bin/python"
VPIP="$VENV/bin/pip"
set +e
BOOTSTRAP_PY="$(pick_python)"
boot_rc=$?
set -e
if [[ "$boot_rc" -ne 0 ]]; then
  BOOTSTRAP_PY=""
fi

if [[ -x "$VPY" ]]; then
  PY="$VPY"
else
  if [[ -z "$BOOTSTRAP_PY" ]]; then
    echo "python3 not found. On a Mac: brew install python@3.12" >&2
    echo "Do not use ~/.venv. This launcher creates and uses $ROOT/.venv only." >&2
    exit 2
  fi
  PY="$BOOTSTRAP_PY"
fi

PY_MAJ="$("$PY" -c 'import sys; print(sys.version_info.major)')"
PY_MIN="$("$PY" -c 'import sys; print(sys.version_info.minor)')"
if [[ "$PY_MAJ" -lt 3 || ( "$PY_MAJ" -eq 3 && "$PY_MIN" -lt 9 ) ]]; then
  echo "Python 3.9+ is required (found $PY $($PY -V 2>&1))." >&2
  echo "On a Mac: brew install python@3.12" >&2
  exit 2
fi
if [[ "$PY_MAJ" -eq 3 && "$PY_MIN" -lt 12 ]]; then
  echo "note: $PY is $($PY -V 2>&1); 3.12 is preferred, continuing with this interpreter." >&2
fi

if [[ ! -x "$VPY" ]]; then
  echo "creating venv at $VENV with $PY"
  set +e
  "$PY" -m venv "$VENV"
  venv_rc=$?
  set -e
  if [[ ! -x "$VPY" ]]; then
    set +e
    "$PY" -m venv --without-pip "$VENV"
    set -e
  fi
  if [[ ! -x "$VPY" ]]; then
    echo "venv python missing at $VPY; refusing to use a python outside $ROOT/.venv" >&2
    echo "Do not use ~/.venv. On a Mac: brew install python@3.12 then rerun:" >&2
    echo "  bash ~/docker-compose-up-d/start.sh" >&2
    exit 2
  elif [[ "$venv_rc" -ne 0 ]]; then
    echo "note: python -m venv reported an error (often missing ensurepip); continuing."
  fi
fi

assert_repo_venv_python() {
  local root_abs vpy_abs home_abs
  root_abs="$(cd "$ROOT" && pwd -P)"
  if [[ ! -x "$VPY" ]]; then
    echo "repo venv python missing: $VPY" >&2
    echo "This launcher only runs $root_abs/.venv/bin/python, never ~/.venv." >&2
    exit 2
  fi
  vpy_abs="$(abs_file "$VPY")"
  case "$vpy_abs" in
    "$root_abs"/.venv/*) ;;
    *)
      echo "refusing python outside the repo venv: $vpy_abs (ROOT=$root_abs)" >&2
      echo "Do not use ~/.venv. Run: bash ~/docker-compose-up-d/start.sh" >&2
      exit 2
      ;;
  esac
  if [[ -n "${HOME:-}" ]]; then
    home_abs="$(cd "$HOME" && pwd -P 2>/dev/null || true)"
    if [[ -n "$home_abs" && "$home_abs" != "$root_abs" ]]; then
      case "$vpy_abs" in
        "$home_abs"/.venv/*)
          echo "refusing home venv $vpy_abs" >&2
          echo "This launcher only runs $root_abs/.venv/bin/python, never ~/.venv." >&2
          exit 2
          ;;
      esac
    fi
  fi
}

write_bitbank_src_pth() {
  local site root_abs site_abs
  root_abs="$(cd "$ROOT" && pwd -P)"
  site="$("$VPY" -c 'import sysconfig; print(sysconfig.get_path("purelib"))')"
  if [[ -z "$site" ]]; then
    echo "cannot locate site-packages for $VPY" >&2
    exit 2
  fi
  mkdir -p "$site"
  site_abs="$(cd "$site" && pwd -P)"
  case "$site_abs" in
    "$root_abs"/.venv/*) ;;
    *)
      echo "refusing to write bitbank_bot_src.pth outside the repo venv (site=$site_abs)" >&2
      echo "This launcher only uses $root_abs/.venv, never ~/.venv." >&2
      exit 2
      ;;
  esac
  printf '%s\n' "$root_abs/src" > "$site_abs/bitbank_bot_src.pth"
}

assert_repo_venv_python
unset PYTHONHOME || true
export VIRTUAL_ENV="$VENV"
export PATH="$VENV/bin:${PATH}"
VPIP="$VENV/bin/pip"

install_reqs() {
  if [[ -n "${VPIP}" && -x "$VPIP" ]]; then
    "$VPIP" install -q -r "$ROOT/requirements.txt"
    return
  fi
  if "$VPY" -m pip --version >/dev/null 2>&1; then
    "$VPY" -m pip install -q -r "$ROOT/requirements.txt"
    return
  fi
  if [[ -n "${BOOTSTRAP_PY:-}" ]] && "$BOOTSTRAP_PY" -m pip --version >/dev/null 2>&1; then
    if is_disallowed_home_venv "$BOOTSTRAP_PY"; then
      echo "refusing pip from ~/.venv; install into $ROOT/.venv only." >&2
      exit 2
    fi
    SITE="$("$VPY" -c 'import sysconfig; print(sysconfig.get_path("purelib"))')"
    mkdir -p "$SITE"
    "$BOOTSTRAP_PY" -m pip install -q -r "$ROOT/requirements.txt" --target "$SITE"
    return
  fi
  echo "pip is not available." >&2
  echo "On a Mac with Homebrew: brew install python@3.12" >&2
  echo "On Debian: sudo apt install python3-venv python3-pip" >&2
  exit 2
}

need_install=0
if ! "$VPY" -c "import dotenv, httpx" >/dev/null 2>&1; then
  need_install=1
fi
if [[ "$need_install" -eq 1 ]]; then
  echo "installing dependencies"
  set +e
  install_reqs
  set -e
fi

oneshot=0
want_stdlib_loop=1
for a in "$@"; do
  case "$a" in
    --once|--check-config|--preflight|--backtest|--help|-h|--max-cycles|--self-test)
      oneshot=1
      want_stdlib_loop=0
      ;;
    --no-supervise)
      want_stdlib_loop=0
      ;;
  esac
done

write_bitbank_src_pth

if ! "$VPY" -c "import dotenv, httpx" >/dev/null 2>&1; then
  echo "pip packages missing; starting stdlib DRY_RUN (python3 run.py, no orders)"
  if [[ ! -f "$ROOT/run.py" ]]; then
    echo "cannot start: missing $ROOT/run.py" >&2
    echo "Do not run CommandLineTools python3 on a file under ~ (test_public.py / main.py)." >&2
    not_in_repo
    exit 2
  fi
  if [[ "$oneshot" -eq 1 || "$want_stdlib_loop" -eq 0 ]]; then
    exec "$VPY" "$ROOT/run.py" "$@"
  fi
  delay=2
  while true; do
    set +e
    "$VPY" "$ROOT/run.py" "$@"
    rc=$?
    set -e
    if [[ "$rc" -eq 0 || "$rc" -eq 130 || "$rc" -eq 143 || "$rc" -eq 2 ]]; then
      if [[ "$rc" -eq 2 ]]; then
        echo "stdlib launcher: fatal exit 2 (not restarting)" >&2
      fi
      exit "$rc"
    fi
    echo "stdlib launcher: crash exit $rc; restart in ${delay}s" >&2
    sleep "$delay"
    delay=$((delay * 2))
    if [[ "$delay" -gt 30 ]]; then
      delay=30
    fi
  done
fi

if [[ ! -f "$ROOT/.env" ]]; then
  if [[ -f "$ROOT/.env.example" ]]; then
    cp "$ROOT/.env.example" "$ROOT/.env"
    echo "wrote $ROOT/.env from .env.example (DRY_RUN=true, keys empty; values not printed)"
  fi
fi

mkdir -p "$ROOT/logs" "$ROOT/data"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

want_screen=0
if [[ -t 1 ]]; then
  want_screen=1
fi
for a in "$@"; do
  case "$a" in
    --once|--check-config|--preflight|--backtest|--no-screen)
      want_screen=0
      ;;
    --screen)
      want_screen=1
      ;;
  esac
done

SCREEN_ARGS=()
if [[ "$want_screen" -eq 1 ]]; then
  has_screen=0
  for a in "$@"; do
    if [[ "$a" == "--screen" ]]; then
      has_screen=1
    fi
  done
  if [[ "$has_screen" -eq 0 ]]; then
    SCREEN_ARGS=(--screen)
  fi
fi

SUPERVISE_ARGS=()
if [[ -n "${INVOCATION_ID:-}" ]]; then
  has_sup=0
  for a in "$@"; do
    case "$a" in
      --supervise|--no-supervise) has_sup=1 ;;
    esac
  done
  if [[ "$has_sup" -eq 0 ]]; then
    SUPERVISE_ARGS=(--no-supervise)
  fi
fi

echo "opening Bitbank BTC/JPY 取引画面 (Ctrl-C to stop)"
echo "HOLD/WAIT is normal. JSON detail is logs/bot.log (rotated; do not dump stdout)"
echo "project_root=$ROOT"
echo "using $VPY"
echo "lock=$ROOT/data/bot.lock kill=$ROOT/data/KILL (create KILL to halt new orders)"

# Default (no extra args): continuous loop + trading screen on a TTY.
# Crash backoff lives in bitbank_bot.launch.
if [[ ! -f "$ROOT/src/bitbank_bot/launch.py" || ! -f "$ROOT/main.py" ]]; then
  echo "cannot start: missing $ROOT/src/bitbank_bot/launch.py or $ROOT/main.py" >&2
  echo "Do not run CommandLineTools python3 on a file under ~ (test_public.py / main.py)." >&2
  not_in_repo
  exit 2
fi
exec "$VPY" -m bitbank_bot.launch "${SUPERVISE_ARGS[@]}" "${SCREEN_ARGS[@]}" "$@"
