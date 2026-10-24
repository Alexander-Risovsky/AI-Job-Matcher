FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY scripts ./scripts

# Install uv from PyPI rather than a second Docker registry image.
# uv resolves/downloads the same pyproject dependencies faster than pip.
RUN python -m pip install --no-cache-dir "uv==0.9.18" \
    && uv pip install --system --no-cache .

# WSL user usually has uid/gid 1000: allow access to the existing Telethon
# SQLite session without changing ownership of its source file.
RUN groupadd --gid 1000 matcher \
    && useradd --uid 1000 --gid 1000 --create-home matcher \
    && mkdir -p /app/data /sessions \
    && chown -R matcher:matcher /app/data /sessions

USER matcher

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-level", "info"]
