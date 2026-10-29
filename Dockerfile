FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts ./scripts
COPY diagnostics.py paste.sh run.py main.py ./
RUN pip install --no-cache-dir . \
    && (pip install --no-cache-dir "sentry-sdk>=2.0.0" || true) \
    && chmod +x scripts/*.py scripts/*.sh paste.sh || true

CMD ["python", "-m", "bitbank_bot", "--no-screen"]
