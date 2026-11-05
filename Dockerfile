# Build stage
FROM python:3.15-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/
# Compile bytecode for faster startup, and copy files out of uv's cache so the
# virtualenv can be copied to the execution stage
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock /app/
RUN uv sync --locked --no-dev --no-cache

# Execution stage
FROM python:3.15-slim
WORKDIR /app
# Retrieve packages from build stage
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
# Source code
COPY src/ /app/src/
# The app doesn't write to disk, so it doesn't need root.
USER nobody
# 1 worker, 4 worker threads should be more than enough.
# --worker-class gthread is automatically set if --threads > 1.
# In my experience this configuration hovers around 100 MB
# baseline (noop app code) memory usage in Cloud Run.
# --timeout 0 disables gunicorn's automatic worker restarting.
# "Workers silent for more than this many seconds are killed and restarted."
# If things get bad you might want to --max-requests, --max-requests-jitter, --workers 2.
CMD ["gunicorn", "--bind", ":8080", "--workers", "1", "--threads", "4", "--timeout", "0", "src.main:create_app()"]
