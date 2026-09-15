#!/usr/bin/env bash
# Install a home launcher that actually starts the bot, plus a zsh/bash function.
#
# After this, `cd ~ && bash ./start.sh` execs the clone's real start.sh.
# It does not run pytest. LIVE is not enabled.
#
#   cd <repo> && bash scripts/install_launch_alias.sh
#
# Then from ~:
#   bash ./start.sh
#   bash ./start.sh --help
#   bash ./start.sh --smoke-order
#   bitbank-start

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

BOT_BRANCH="cursor/closed-loop-launcher-563e"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/.." && pwd)"

if [[ ! -f "$root/start.sh" || ! -f "$root/src/bitbank_bot/launch.py" ]]; then
  echo "cd to the repo first, then run: bash scripts/install_launch_alias.sh" >&2
  echo "Typical clone name: docker-compose-up-d" >&2
  echo "Need branch $BOT_BRANCH (git ls-files start.sh must print start.sh)." >&2
  exit 2
fi

home="${HOME:-}"
if [[ -z "$home" ]]; then
  echo "HOME is unset; cannot install a home launcher" >&2
  exit 2
fi
mkdir -p "$home"

dest="$home/start.sh"
if [[ -e "$dest" && "${1:-}" != "--force" ]]; then
  if ! grep -q "Installed Bitbank launcher" "$dest" 2>/dev/null \
    && ! grep -q "Home-safe start.sh finder" "$dest" 2>/dev/null; then
    echo "refusing to overwrite $dest (not our launcher). Re-run with --force to replace." >&2
    exit 2
  fi
fi

cat >"$dest" <<EOF
#!/usr/bin/env bash
# Installed Bitbank launcher (program-triggered). Execs the clone start.sh.
# Repo baked in at install time. Does not enable LIVE.
set -euo pipefail
REPO="$root"
if [[ ! -f "\$REPO/start.sh" || ! -f "\$REPO/src/bitbank_bot/launch.py" ]]; then
  echo "cd to the repo first, then run: bash ./start.sh" >&2
  echo "Expected clone at: \$REPO (branch $BOT_BRANCH)" >&2
  exit 2
fi
echo "launching Bitbank bot from \$REPO"
exec bash "\$REPO/start.sh" "\$@"
EOF
chmod +x "$dest"

marker="# bitbank-bot launch alias ($BOT_BRANCH)"
snippet=$(cat <<EOF
$marker
bitbank-start() {
  local repo="$root"
  if [ ! -f "\$repo/start.sh" ] || [ ! -f "\$repo/src/bitbank_bot/launch.py" ]; then
    echo "cd to the repo first, then run: bash ./start.sh" >&2
    echo "Expected clone at: \$repo (branch $BOT_BRANCH)" >&2
    return 2
  fi
  cd "\$repo" || return 2
  bash ./start.sh "\$@"
}
EOF
)

install_rc() {
  local rc="$1"
  if [[ -f "$rc" ]] && grep -Fq "$marker" "$rc"; then
    echo "alias already present in $rc"
    return 0
  fi
  {
    echo ""
    echo "$snippet"
  } >>"$rc"
  echo "appended bitbank-start to $rc"
}

install_rc "$home/.zshrc"
install_rc "$home/.bashrc"

echo "installed home launcher: $dest"
echo "from ~ this execs: bash $root/start.sh"
echo "examples:"
echo "  bash $dest --help"
echo "  bash $dest --smoke-order"
echo "  bash $dest --execute"
echo "  bash $root/run_transaction.sh"
echo "  bash $dest --screen"
echo "or open a new shell and run: bitbank-start"
echo "pytest is not a launch step. Tests: bash $root/scripts/run_tests.sh"
