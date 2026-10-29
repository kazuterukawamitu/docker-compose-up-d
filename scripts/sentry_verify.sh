#!/usr/bin/env bash
# zsh-safe Sentry check. Do NOT paste Python `import` lines into the shell.
#
# Ultra-fast paste (one line) on MacBook Air iTerm:
#   export SENTRY_DSN='https://YOUR_KEY@oXXXX.ingest.sentry.io/YYYY'
#   curl -fsSL https://raw.githubusercontent.com/kazuterukawamitu/docker-compose-up-d/cursor/complete-bot-quantum-sentry-9d40/scripts/sentry_verify.sh | bash
#
# Or locally:
#   SENTRY_DSN='...' bash scripts/sentry_verify.sh
# Optional intentional error to appear in Sentry:
#   SENTRY_VERIFY_ERROR=1 SENTRY_DSN='...' bash scripts/sentry_verify.sh
set -euo pipefail

if [[ -z "${SENTRY_DSN:-}" ]]; then
  echo "SENTRY_DSN is empty." >&2
  echo "export SENTRY_DSN='https://<key>@o<org>.ingest.sentry.io/<project>'" >&2
  echo "Then re-run this script. Do not paste Python into zsh." >&2
  exit 2
fi

python3 -m pip install -q --user 'sentry-sdk>=2.0.0' >/dev/null 2>&1 || true

python3 - <<'PY'
import os
import sys

try:
    import sentry_sdk
except ImportError:
    print("sentry-sdk not installed; run: python3 -m pip install --user sentry-sdk", file=sys.stderr)
    raise SystemExit(3)

dsn = os.environ["SENTRY_DSN"].strip()
sentry_sdk.init(dsn=dsn, send_default_pii=False, traces_sample_rate=0.0)
print("sentry ok: init succeeded")
if os.environ.get("SENTRY_VERIFY_ERROR", "").strip().lower() in {"1", "true", "yes", "on"}:
    print("sending intentional ZeroDivisionError to Sentry…")
    1 / 0
PY
