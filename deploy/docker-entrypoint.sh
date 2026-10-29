#!/bin/sh
# Ensure bind-mounted ./data and ./logs are writable by the bot user (uid 10001).
# Host dirs created by the deploy user are otherwise owned by root/deploy and
# cause PermissionError under USER bot.
# Never fall back to world-writable mounts: data holds KILL_SWITCH_PATH / STATE_PATH.
set -eu

mkdir -p /app/data /app/logs

if [ "$(id -u)" -eq 0 ]; then
  if ! chown -R bot:bot /app/data /app/logs 2>/dev/null; then
    echo "docker-entrypoint: chown bot:bot failed for /app/data /app/logs" >&2
    echo "docker-entrypoint: run deploy/vps_up.sh (chown 10001) or fix mount ownership" >&2
  fi
  chmod -R ug+rwX,o-rwx /app/data /app/logs 2>/dev/null || true
  if command -v setpriv >/dev/null 2>&1; then
    exec setpriv --reuid=bot --regid=bot --clear-groups -- "$@"
  fi
  if command -v runuser >/dev/null 2>&1; then
    exec runuser -u bot -- "$@"
  fi
  # Include $0 so `python -m bitbank_bot` is not shifted to `-m bitbank_bot`.
  exec su -s /bin/sh bot -c 'exec "$0" "$@"' -- "$@"
fi

exec "$@"
