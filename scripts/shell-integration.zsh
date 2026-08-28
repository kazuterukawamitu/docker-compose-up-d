# Bitbank bot zsh helpers. Source from ~/.zshrc if you want:
#   source /path/to/docker-compose-up-d/scripts/shell-integration.zsh
#
# HIST_VERIFY: history expansion is shown for confirmation instead of running immediately.
# Do not paste Python into zsh — run the module instead:
#   PYTHONPATH=src python3 -m bitbank_bot --once

setopt HIST_VERIFY

_BITBANK_BOT_ROOT="${0:A:h:h}"

if [[ -d "${_BITBANK_BOT_ROOT}/.venv" ]]; then
  typeset -U path
  path=("${_BITBANK_BOT_ROOT}/.venv/bin" $path)
fi

bitbank-bot() {
  (
    cd "${_BITBANK_BOT_ROOT}" || return
    if [[ -d .venv ]]; then
      # shellcheck disable=SC1091
      source .venv/bin/activate
    fi
    PYTHONPATH=src python3 -m bitbank_bot "$@"
  )
}
