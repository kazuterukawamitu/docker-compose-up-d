FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends locales \
    && sed -i '/ja_JP.UTF-8/s/^# //g' /etc/locale.gen \
    && locale-gen ja_JP.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=ja_JP.UTF-8 \
    LANGUAGE=ja_JP:ja \
    LC_ALL=ja_JP.UTF-8 \
    TZ=Japan \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    DRY_RUN=true \
    LIVE_TRADING=false

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src /app/src
COPY scripts /app/scripts

RUN mkdir -p /app/logs /app/data

CMD ["python3", "-m", "bitbank_bot"]
