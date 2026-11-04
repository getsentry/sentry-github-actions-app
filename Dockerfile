# Every dependency installs from a prebuilt wheel, so a separate build stage saves nothing.
FROM python:3.11-slim
WORKDIR /app
COPY requirements.frozen.txt .
RUN pip install --no-cache-dir -r requirements.frozen.txt
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
