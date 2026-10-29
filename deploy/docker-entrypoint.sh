#!/bin/sh
# Ensure bind-mounted ./data and ./logs are writable by the bot user (uid 10001).
# Host dirs created by the deploy user are otherwise owned by root/deploy and
# cause PermissionError under USER bot.
set -eu

mkdir -p /app/data /app/logs

if [ "$(id -u)" -eq 0 ]; then
  if chown -R bot:bot /app/data /app/logs 2>/dev/null; then
    :
  else
    chmod -R a+rwX /app/data /app/logs
  fi
  if command -v setpriv >/dev/null 2>&1; then
    exec setpriv --reuid=bot --regid=bot --clear-groups -- "$@"
  fi
  if command -v runuser >/dev/null 2>&1; then
    exec runuser -u bot -- "$@"
  fi
  exec su -s /bin/sh bot -c 'exec "$0" "$@"' -- "$@"
fi

exec "$@"
