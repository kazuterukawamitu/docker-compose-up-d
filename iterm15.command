#!/bin/bash
# Double-click in Finder, or run from iTerm. Works from any directory.
# Never enables LIVE.

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$DIR/iterm15" ]; then
  exec /usr/bin/env python3 "$DIR/iterm15" "$@"
fi
if [ -f "$DIR/run.py" ]; then
  exec /usr/bin/env python3 "$DIR/run.py" "$@"
fi
if [ -f "$HOME/iterm15" ]; then
  exec /usr/bin/env python3 "$HOME/iterm15" "$@"
fi
echo "iterm15 / run.py not found. In iTerm paste:" >&2
echo "  curl -fsSL https://raw.githubusercontent.com/kazuterukawamitu/docker-compose-up-d/cursor/closed-loop-runtime-hardening/iterm15 -o \"\$HOME/iterm15\" && python3 \"\$HOME/iterm15\"" >&2
exit 2
