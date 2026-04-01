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

# Default command: API (override in Railway for worker)
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
