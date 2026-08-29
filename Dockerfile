# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Enable unbuffered stdout
ENV PYTHONUNBUFFERED=1

# Set workdir
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install pip, dependencies, and Python project
COPY pyproject.toml .
COPY backend ./backend
COPY setup ./setup
COPY .env.example ./
RUN pip install --upgrade pip && \
    pip install hatchling && \
    pip install .

# Copy static, templates, and any base code
COPY backend/gateway/templates ./backend/gateway/templates
COPY backend/gateway/static ./backend/gateway/static

# Expose port (Railway/uvicorn default)
EXPOSE 8000

# Default command
CMD [ "uvicorn", "backend.gateway.main:app", "--host", "0.0.0.0", "--port", "8000" ]
