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

ENV PYTHONPATH=/app/apps/simulation-worker:/app/apps/api
CMD ["python", "-m", "hydra_worker.worker"]
