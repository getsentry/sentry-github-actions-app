# Build stage
FROM python:3.11-slim AS builder
RUN pip install -U pip setuptools wheel
# Copy files
COPY requirements.frozen.txt /project/
WORKDIR /project
RUN pip install --no-cache-dir -r requirements.frozen.txt

# Execution stage
FROM python:3.11-slim
# Send output to Cloud Run logs right away instead of buffering it.
ENV PYTHONUNBUFFERED=1
# Cloud Run sets PORT. Without --bind, gunicorn listens on 0.0.0.0:$PORT.
ENV PORT=8080
WORKDIR /app
COPY src/ /project/src
# Retrieve packages from build stage
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
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
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--timeout", "0", "src.main:app"]
