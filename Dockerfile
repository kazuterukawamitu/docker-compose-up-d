# Local DRY_RUN image. Do not copy .env into this image and do not point it at a live VPS.
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt pyproject.toml ./
COPY src ./src
COPY run.py ./
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH=/app/src
ENV DRY_RUN=true
ENV LIVE_TRADING=false
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "bitbank_bot", "--once", "--synthetic", "--no-screen", "--skip-lock"]
