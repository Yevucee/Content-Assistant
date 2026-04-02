FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV BRANDS_ROOT=/app/brands

RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY harness ./harness
COPY apps ./apps
COPY brands ./brands

RUN pip install --no-cache-dir -U pip && pip install --no-cache-dir .

RUN mkdir -p /app/data

# API: Railway sets PORT; local / compose default 8000
# Worker on Railway: override start command to `python -m apps.worker.main`
CMD ["/bin/sh", "-c", "exec uvicorn apps.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
