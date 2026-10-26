FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Default is DRY_RUN. Live orders require DRY_RUN=false, LIVE_TRADING=true, and API keys.
CMD ["python", "-m", "bitbank_bot", "--dry-run", "--no-screen"]
