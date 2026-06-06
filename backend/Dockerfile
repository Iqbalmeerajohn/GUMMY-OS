# GUMMY OS backend — production image.
# Uses uv for fast, reproducible installs. Runtime deps only (no dev group).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Bring in the uv binary.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Project metadata first for better layer caching; README is referenced by
# pyproject (readme = "README.md") so it must be present during the build.
COPY pyproject.toml README.md ./
COPY app ./app

RUN uv sync --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
