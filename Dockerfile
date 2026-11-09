# Each image is pinned to its multi-arch index digest, so CI scans the same image
# that Cloud Build later ships. The tag only documents what the digest is, and
# Dependabot proposes a new digest when the tag gets rebuilt.

# Dependabot only updates images in FROM lines, not in COPY --from, so uv gets
# its own stage.
FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv

# Build stage
FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2 AS builder
COPY --from=uv /uv /bin/
# Compile bytecode for faster startup, and copy files out of uv's cache so the
# virtualenv can be copied to the execution stage
# The execution stage has no Python, so use a uv-managed one under a fixed path
# that gets copied over too. Pinning only the minor version lets each uv release
# (bumped by Dependabot) bring the latest Python patch release.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    UV_PYTHON=3.15 UV_PYTHON_PREFERENCE=only-managed UV_PYTHON_INSTALL_DIR=/python
RUN uv python install
# Drop what a webhook server never uses: headers, docs, pip, and Tcl/Tk
RUN cd "$UV_PYTHON_INSTALL_DIR"/cpython-"$UV_PYTHON"-*/ \
 && rm -rf include share bin/idle* bin/pip* lib/*tcl* lib/*tk* lib/thread* \
      lib/python3.*/site-packages/pip* lib/python3.*/ensurepip lib/python3.*/idlelib \
      lib/python3.*/tkinter lib/python3.*/turtledemo lib/python3.*/lib-dynload/_tkinter*
WORKDIR /app
COPY pyproject.toml uv.lock /app/
RUN uv sync --locked --no-dev --no-cache

# Execution stage
# Distroless has glibc and the C++ runtime that grpcio needs, but no shell or
# package manager, so far fewer OS packages to carry vulnerabilities.
# The nonroot tag runs as an unprivileged user; the app doesn't write to disk.
FROM gcr.io/distroless/cc-debian13:nonroot@sha256:cc66d222f0a7ec996b78a99fe76a969bc80b539a5016ad866c14d1949bc6d0ab
# Send output to Cloud Run logs right away instead of buffering it.
ENV PYTHONUNBUFFERED=1
# Cloud Run sets PORT. Without --bind, gunicorn listens on 0.0.0.0:$PORT.
ENV PORT=8080
WORKDIR /app
# Retrieve Python and packages from build stage
COPY --from=builder /python /python
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
# Source code
COPY src/ /app/src/
# 1 worker, 4 worker threads should be more than enough.
# --worker-class gthread is automatically set if --threads > 1.
# In my experience this configuration hovers around 100 MB
# baseline (noop app code) memory usage in Cloud Run.
# --timeout 0 disables gunicorn's automatic worker restarting.
# "Workers silent for more than this many seconds are killed and restarted."
# If things get bad you might want to --max-requests, --max-requests-jitter, --workers 2.
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--timeout", "0", "src.main:create_app()"]
