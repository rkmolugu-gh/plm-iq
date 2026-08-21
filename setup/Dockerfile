# syntax=docker/dockerfile:1.7

FROM python:3.10-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    UV_LINK_MODE=copy

WORKDIR /app

# Runtime libraries only. Add OS packages here if future document/CAD
# processing dependencies require them.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /uvx /usr/local/bin/

COPY ..\pyproject.toml uv.lock* ./

RUN uv sync --frozen --no-dev

COPY app ./app
COPY db ./db
COPY plmassistant ./plmassistant
COPY aisearch ./aisearch

# Application-owned writable directories.
RUN mkdir -p /app/data /app/data/downloads /app/app/static

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
