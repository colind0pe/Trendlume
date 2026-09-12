# ==============================================================================
# Trendlume - Single Container Dockerfile
# Includes Python 3.12, FFmpeg, and uv for AI media execution
# ==============================================================================

FROM python:3.12-slim-bookworm

# 1. Install system utilities and FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# 2. Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 3. Copy backend configuration and install dependencies
COPY backend/pyproject.toml backend/uv.lock /app/backend/
WORKDIR /app/backend
RUN uv sync --frozen --no-dev

# Playwright is the single renderer for template previews and final frames.
# Install its pinned Chromium build and Linux dependencies in the image so
# production does not silently fall back to a placeholder frame.
RUN uv run playwright install --with-deps chromium

# 4. Copy application source code
COPY backend/src /app/backend/src
COPY backend/alembic /app/backend/alembic
COPY backend/templates /app/backend/templates
COPY backend/resources /app/backend/resources
COPY backend/workflows /app/backend/workflows
COPY backend/alembic.ini /app/backend/alembic.ini
COPY docker/entrypoint.sh /usr/local/bin/trendlume-entrypoint

# 5. Create application storage directory
RUN sed -i 's/\r$//' /usr/local/bin/trendlume-entrypoint \
    && mkdir -p /app/data \
    && chmod +x /usr/local/bin/trendlume-entrypoint

ENV HOST="0.0.0.0"
ENV PORT=8000
ENV DATA_DIR="/app/data"
ENV PATH="/app/backend/.venv/bin:$PATH"

EXPOSE 8000

# 6. Start FastAPI Application
# Apply additive schema migrations on deploy (never delete data), then start
# the API. Development database destruction remains an explicit script action.
ENTRYPOINT ["/usr/local/bin/trendlume-entrypoint"]
