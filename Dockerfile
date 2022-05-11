# Build stage
FROM python:3.8.10 AS builder
RUN pip install -U pip setuptools wheel
# Copy files
COPY requirements.txt /project/
WORKDIR /project
RUN pip install --no-cache-dir -r requirements.txt

# Execution stage
FROM python:3.8
WORKDIR /app
COPY src/ /project/src
# Retrieve packages from build stage
COPY --from=builder /usr/local/lib/python3.8/site-packages/ /usr/local/lib/python3.8/site-packages/
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
