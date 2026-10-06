# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# Backend Dockerfile — installs uv, syncs deps, runs with uvicorn
# Listens on Railway's dynamic $PORT (defaults to 8000 locally)
# ---------------------------------------------------------------------------

FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Sync production deps (no dev extras, frozen lockfile)
RUN uv sync --frozen --no-dev

# Copy the rest of the application
COPY . .

# Run Alembic migrations then start the server
# Railway sets $PORT; default to 8000 for local use
CMD uv run alembic upgrade head && \
    uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
