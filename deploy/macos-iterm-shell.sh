# Optional macOS iTerm2 / zsh helpers for this repo.
# Do not replace your full ~/.zshrc. Source from the project directory:
#   source deploy/macos-iterm-shell.sh
#
# `python3 main.py` from ~ fails because main.py is not in $HOME.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
export PATH="$PROJECT_ROOT/.venv/bin:$PATH"
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  . "$PROJECT_ROOT/.venv/bin/activate"
fi
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

bitbank-start() {
  bash "$PROJECT_ROOT/start.sh" --screen "$@"
}

bitbank-once() {
  DRY_RUN=true LIVE_TRADING=false ENABLE_WEBSOCKET=false \
    bash "$PROJECT_ROOT/start.sh" --once --skip-lock --no-screen "$@"
}
