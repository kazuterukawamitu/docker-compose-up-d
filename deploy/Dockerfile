FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    LANG=C.UTF-8

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src

RUN useradd --create-home --uid 10001 bot \
    && mkdir -p /app/logs /app/state \
    && chown -R bot:bot /app
USER bot

CMD ["python", "-m", "bitbank_bot"]
