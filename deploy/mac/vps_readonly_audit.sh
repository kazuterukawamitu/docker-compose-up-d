#!/usr/bin/env bash
# Read-only VPS audit. Run ON the VPS (after scp), not by pasting Python into zsh.
#   scp deploy/mac/vps_readonly_audit.sh rocky@49.212.212.148:/tmp/
#   ssh rocky@49.212.212.148 'bash /tmp/vps_readonly_audit.sh'
set -u
umask 077

BOT=/home/rocky/bitbank-bot
XFER=/home/rocky/bitbank-transfer-8delgk87
BACKUPS=/home/rocky/bitbank-backups

echo "===== BITBANK READONLY AUDIT ====="
date -Is
hostname

echo
echo "===== 1. SERVICE ====="
systemctl show bitbank-bot.service -p MainPID -p ActiveState -p SubState -p ExecStart 2>/dev/null || true

echo
echo "===== 2. PROCESSES ====="
pgrep -af 'bitbank_bot|launch.py|launch.sh' || true

echo
echo "===== 3. DRY-RUN TRANSFER TREE ====="
if [ -d "$XFER" ]; then
  ls -ld "$XFER"
  if [ -d /proc/634891 ]; then
    echo "PID634891_CWD=$(readlink /proc/634891/cwd 2>/dev/null || true)"
    echo "PID634891_EXE=$(readlink /proc/634891/exe 2>/dev/null || true)"
    ps -p 634891 -o pid,ppid,etime,args 2>/dev/null || true
    ps -p 634873 -o pid,ppid,etime,args 2>/dev/null || true
  fi
else
  echo "transfer tree missing"
fi

echo
echo "===== 4. SOURCE HASHES (canonical bot dir) ====="
if [ -d "$BOT/src/bitbank_bot" ]; then
  cd "$BOT"
  sha256sum \
    src/bitbank_bot/engine.py \
    src/bitbank_bot/orders.py \
    src/bitbank_bot/strategy.py \
    src/bitbank_bot/config.py \
    src/bitbank_bot/trade_policy.py \
    src/bitbank_bot/profit_inventory.py \
    2>/dev/null || true
else
  echo "BOT dir missing: $BOT"
fi

echo
echo "===== 5. OOS PROTOCOL ====="
OOS="$BOT/data/validation/buy3_forward_oos_protocol.json"
if [ -f "$OOS" ]; then
  python3 -m json.tool "$OOS" | head -120
else
  echo "missing $OOS"
fi

echo
echo "===== 6. BACKUPS ====="
ls -lah "$BACKUPS" 2>/dev/null || true
for A in "$BACKUPS"/bitbank-source-*.tar.gz "$BACKUPS"/clean-*.tar.gz "$BACKUPS"/audit-*.tar.gz; do
  [ -e "$A" ] || continue
  if gzip -t "$A" 2>/dev/null; then
    echo "GZIP_OK $A"
  else
    echo "GZIP_FAIL $A"
  fi
done

echo
echo "===== 7. GIT (if any) ====="
if [ -d "$BOT/.git" ]; then
  (cd "$BOT" && git status --short && git rev-parse --short HEAD)
else
  echo "no git in $BOT"
fi

echo
echo "===== READONLY COMPLETE ====="
echo "NOTE: inactive systemd + --dry-run transfer process means LIVE orders are NOT running."
