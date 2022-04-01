# Build stage
FROM python:3.8.10 AS builder
# Install PDM
RUN pip install -U pip setuptools wheel
RUN pip install pdm
# Copy files
COPY pyproject.toml pdm.lock README.md /project/
COPY src/ /project/src
# Install dependencies and project
WORKDIR /project
RUN pdm install --prod --no-lock --no-editable

# Execution stage
FROM python:3.8
WORKDIR /app
# Retrieve packages from build stage
ENV PYTHONPATH=/project/pkgs
COPY --from=builder /project/__pypackages__/3.8/lib /project/pkgs
RUN pip install gunicorn==20.1.0
# Source code
COPY src/ /app/src/
# 1 worker, 4 worker threads should be more than enough.
# --worker-class gthread is automatically set if --threads > 1.
# In my experience this configuration hovers around 100 MB
# baseline (noop app code) memory usage in Cloud Run.
# --timeout 0 disables gunicorn's automatic worker restarting.
# "Workers silent for more than this many seconds are killed and restarted."
# If things get bad you might want to --max-requests, --max-requests-jitter, --workers 2.
CMD ["gunicorn", "--bind", ":8080", "--workers", "1", "--threads", "4", "--timeout", "0", "src.main:app"]
