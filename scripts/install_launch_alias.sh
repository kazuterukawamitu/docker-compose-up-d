#!/usr/bin/env bash
# Install a home-safe ./start.sh finder and a zsh/bash function.
#
# After this, `cd ~ && bash ./start.sh` prints "cd to the repo" instead of
# bash's raw "No such file or directory". It does not start the bot from ~.
# It does not run pytest. LIVE is not enabled.
#
#   cd <repo> && bash scripts/install_launch_alias.sh
#
# Then either:
#   cd ~/docker-compose-up-d && bash ./start.sh
# or:
#   bitbank-start

if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi

set -euo pipefail

BOT_BRANCH="cursor/bitbank-closed-loop-f964"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/.." && pwd)"
finder="$here/home_start.sh"

if [[ ! -f "$root/start.sh" || ! -f "$root/src/bitbank_bot/launch.py" || ! -f "$finder" ]]; then
  echo "cd to the repo first, then run: bash scripts/install_launch_alias.sh" >&2
  echo "Typical clone name: docker-compose-up-d" >&2
  echo "Need branch $BOT_BRANCH (git ls-files start.sh must print start.sh)." >&2
  exit 2
fi

home="${HOME:-}"
if [[ -z "$home" ]]; then
  echo "HOME is unset; cannot install a home-safe start.sh" >&2
  exit 2
fi
mkdir -p "$home"

dest="$home/start.sh"
if [[ -e "$dest" && "${1:-}" != "--force" ]]; then
  if ! grep -q "Home-safe start.sh finder" "$dest" 2>/dev/null; then
    echo "refusing to overwrite $dest (not our finder). Re-run with --force to replace." >&2
    exit 2
  fi
fi
cp "$finder" "$dest"
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

echo "installed home-safe finder: $dest"
echo "from ~ this prints a cd hint (it does not launch the bot)"
echo "from the clone, start with:"
echo "  cd $root && bash ./start.sh"
echo "or from ~: bash $root/start.sh"
echo "or open a new shell and run: bitbank-start"
echo "pytest is not a launch step. Tests: bash $root/scripts/run_tests.sh"
