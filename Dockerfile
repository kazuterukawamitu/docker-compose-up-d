# Bitbank BTC/JPY bot — Sakura VPS / Docker Agent friendly image.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md ./
COPY src ./src
COPY run.py main.py start.sh diagnostics.py ./
COPY deploy ./deploy
COPY scripts ./scripts

RUN useradd --create-home --uid 10001 bot \
    && mkdir -p /app/data /app/logs \
    && chown -R bot:bot /app \
    && chmod +x /app/deploy/docker-entrypoint.sh /app/start.sh

# Stay root in the image so the entrypoint can chown bind mounts, then drop to bot.
ENTRYPOINT ["/app/deploy/docker-entrypoint.sh"]
# Default stays DRY_RUN. Live needs DRY_RUN=false LIVE_TRADING=true and keys via env.
CMD ["python", "-m", "bitbank_bot"]
