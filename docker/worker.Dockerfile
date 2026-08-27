# Hydra World — simulation worker
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY apps/simulation-worker/requirements.txt /app/apps/simulation-worker/requirements.txt
RUN pip install --no-cache-dir -r /app/apps/simulation-worker/requirements.txt

COPY packages /app/packages
COPY apps/simulation-worker /app/apps/simulation-worker
COPY apps/api /app/apps/api
COPY scripts /app/scripts

RUN python /app/scripts/install_dev_paths.py

ENV PYTHONPATH=/app/apps/simulation-worker:/app/apps/api PORT=8080
EXPOSE 8080

# `service` rather than `worker`: it runs the same loop but answers a health check, which is
# what keeps the container alive on a platform that only understands requests.
CMD exec python -m hydra_worker.service
