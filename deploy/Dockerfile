FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends locales \
    && locale-gen ja_JP.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=ja_JP.UTF-8
ENV LANGUAGE=ja_JP:ja
ENV LC_ALL=ja_JP.UTF-8
ENV TZ=Asia/Tokyo
ENV PYTHONUNBUFFERED=1

COPY requirements.txt pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir .

COPY docs ./docs

RUN useradd --create-home --uid 10001 bot \
    && mkdir -p /app/logs /app/data \
    && chown -R bot:bot /app
USER bot

CMD ["python", "-m", "bitbank_bot"]
